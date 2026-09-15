import pytest

from app.database import Database


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg"])
def test_postgresql_url_loads_driver_without_connecting(monkeypatch, scheme):
    monkeypatch.setenv(
        "DATABASE_URL",
        f"{scheme}://pairroom:p%40ss@localhost:5432/pairroom?sslmode=require",
    )
    database = Database()
    try:
        assert database.engine.dialect.name == "postgresql"
        assert database.engine.dialect.driver == "psycopg"
        args, kwargs = database.engine.dialect.create_connect_args(database.engine.url)
        assert kwargs["password"] == "p@ss"
        assert kwargs["sslmode"] == "require"
        assert "check_same_thread" not in kwargs
    finally:
        database.close()
