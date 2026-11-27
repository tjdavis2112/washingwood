"""Owner mapping: the hand-maintained owners.yaml that ties ESPN member accounts to Owners (ADR-0005).

    owners:
      - name: Quinn Harrow          # display name, unique
        espn_members:               # every ESPN account this person has used
          - "{11111111-...}"
          - "{22222222-...}"

The file holds real names and ESPN IDs, so it lives in the private archive repo (ADR-0007).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml


class OwnerMappingError(ValueError):
    """owners.yaml is malformed, or a Franchise has no mapped Owner."""


@dataclass(frozen=True)
class Owner:
    name: str
    slug: str
    espn_members: tuple[str, ...]


def slugify(name: str) -> str:
    """'Quinn Harrow' -> 'quinn-harrow'. Stable: the site's Owner URLs depend on it."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


class OwnerMap:
    def __init__(self, owners: list[Owner]):
        self.owners = owners
        self._by_member: dict[str, Owner] = {}
        for owner in owners:
            for member in owner.espn_members:
                self._by_member[member.upper()] = owner

    def for_member(self, member_id: str) -> Owner | None:
        # ESPN writes member IDs as "{GUID}"; compare case-insensitively
        return self._by_member.get(member_id.upper())


def load_owners(path: Path) -> OwnerMap:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries = doc.get("owners")
    if not isinstance(entries, list) or not entries:
        raise OwnerMappingError(f"{path}: expected a non-empty 'owners' list")

    owners, names, slugs, members = [], set(), set(), {}
    for i, entry in enumerate(entries):
        name = (entry or {}).get("name")
        ids = (entry or {}).get("espn_members") or []
        if not isinstance(name, str) or not name.strip():
            raise OwnerMappingError(f"{path}: owners[{i}] has no name")
        if not isinstance(ids, list) or not all(isinstance(m, str) and m for m in ids):
            raise OwnerMappingError(f"{path}: {name} needs 'espn_members' as a list of member IDs")
        name = name.strip()
        slug = slugify(name)
        if name in names or slug in slugs:
            raise OwnerMappingError(f"{path}: Owner name {name!r} is listed twice (or collides with another slug)")
        for m in ids:
            if m.upper() in members:
                raise OwnerMappingError(f"{path}: member {m} is mapped to both {members[m.upper()]} and {name}")
            members[m.upper()] = name
        names.add(name)
        slugs.add(slug)
        owners.append(Owner(name=name, slug=slug, espn_members=tuple(ids)))
    return OwnerMap(owners)
