"""Shared fixtures. Seam 1 tests get a fresh Postgres database each, inside one throwaway
postgres:16 container per test session (testcontainers). Needs Docker Desktop running."""

import uuid

import psycopg
import pytest


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
