"""Shared fixtures. Seam 1 tests get a fresh Postgres database each, inside one throwaway
postgres:16 container per test session (testcontainers). Needs Docker Desktop running."""

import uuid

import psycopg
import pytest
from espn_fixture import default_owners, write_owners


def _docker_reachable() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def pg_server():
    if not _docker_reachable():
        pytest.skip("Docker isn't reachable: start Docker Desktop to run the Postgres-backed tests")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver=None) as pg:
        yield pg


@pytest.fixture
def pg_dsn(pg_server):
    """DSN of a brand-new, empty database."""
    admin = pg_server.get_connection_url()
    name = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    yield admin.rsplit("/", 1)[0] + f"/{name}"


@pytest.fixture
def archive(tmp_path):
    """Where a test writes its fixture Seasons (archive/<league-id>/<year>/)."""
    return tmp_path / "archive" / "999001"


@pytest.fixture
def owners(tmp_path):
    """owners.yaml mapping every invented person to their member ID."""
    return write_owners(tmp_path / "owners.yaml", default_owners())
