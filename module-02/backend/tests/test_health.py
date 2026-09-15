from sqlalchemy.exc import OperationalError


def test_health_checks_database_without_authentication(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_hides_database_failure_and_recovers(client, monkeypatch):
    def fail():
        raise OperationalError("SELECT 1", {}, Exception("private connection details"))

    with monkeypatch.context() as patch:
        patch.setattr(client.app.state.database.engine, "connect", fail)
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
    assert client.get("/health").status_code == 200
