"""Validate documents against the site-data contract (contract/site-data.schema.json).

The contract is the interface between the pipeline (Python) and the site (Astro).
The schema has one entry point per document kind under `$defs`; see contract/README.md.

    from washingwood.contract import validate
    validate(doc, "season")  # raises ContractError listing every violation
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

# src/washingwood/contract.py -> repo root/contract
CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contract"
SCHEMA_PATH = CONTRACT_DIR / "site-data.schema.json"
EXAMPLES_DIR = CONTRACT_DIR / "examples"

# Document kinds: each is an entry point under the schema's $defs
KINDS = (
    "league",
    "trophyShelf",
    "ownerIndex",
    "owner",
    "season",
    "draft",
    "matchups",
    "rivalry",
    "boxScores",
    "recordBook",
    "transactions",
)


class ContractError(ValueError):
    """A document doesn't match the site-data contract. `errors` lists each violation."""

    def __init__(self, kind: str, errors: list[str]):
        self.kind = kind
        self.errors = errors
        super().__init__(f"{kind} document breaks the site-data contract:\n" + "\n".join(f"  - {e}" for e in errors))


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@cache
def _validator(kind: str) -> Draft202012Validator:
    schema = load_schema()
    # Point at one entry point while keeping $defs resolvable from the same root
    entry = {"$ref": f"#/$defs/{kind}", "$defs": schema["$defs"]}
    Draft202012Validator.check_schema(entry)
    return Draft202012Validator(entry)


def validate(doc: object, kind: str) -> None:
    """Raise ContractError if `doc` isn't a valid `kind` document."""
    if kind not in KINDS:
        raise ValueError(f"unknown document kind {kind!r}; expected one of {KINDS}")
    errors = sorted(_validator(kind).iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        raise ContractError(kind, [f"{_path(e)}: {e.message}" for e in errors])


def _path(error) -> str:
    return "/" + "/".join(str(p) for p in error.absolute_path)
