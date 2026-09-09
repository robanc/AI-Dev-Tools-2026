from fastapi.testclient import TestClient
import os
from pathlib import Path
import subprocess
import sys

from app.main import create_app


def test_create_edit_move_and_delete_survive_restart(tmp_path):
    url = 'sqlite:///' + (tmp_path / 'persistent.db').as_posix()
    with TestClient(create_app(url)) as client:
        task = client.post('/api/tasks', json={'title': 'Saved'}).json()
        deleted = client.post('/api/tasks', json={'title': 'Remove me'}).json()
        response = client.patch(f"/api/tasks/{task['id']}", json={
            'title': 'Edited', 'description': 'Persistent details', 'status': 'done',
        })
        assert response.status_code == 200
        expected = response.json()
        assert client.delete(f"/api/tasks/{deleted['id']}").status_code == 204
    # A fresh engine and app reopen the same database after full shutdown.
    with TestClient(create_app(url)) as restarted:
        assert restarted.get('/api/tasks').json() == [expected]
        assert restarted.delete(f"/api/tasks/{task['id']}").status_code == 204
    with TestClient(create_app(url)) as restarted:
        assert restarted.get('/api/tasks').json() == []
        assert restarted.post('/api/tasks', json={'title': 'Next'}).json()['id'] > deleted['id']


def test_environment_database_configuration(tmp_path, monkeypatch):
    path = tmp_path / 'configured.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
    with TestClient(create_app()) as client:
        assert client.post('/api/tasks', json={'title': 'Configured'}).status_code == 201
    assert path.is_file()
    with TestClient(create_app()) as client:
        assert client.get('/api/tasks').json()[0]['title'] == 'Configured'


def test_persistence_across_python_processes(tmp_path):
    environment = {**os.environ, 'DATABASE_URL': 'sqlite:///' + (tmp_path / 'process.db').as_posix()}
    prefix = 'from fastapi.testclient import TestClient\nfrom app.main import create_app\n'
    scripts = [
        "with TestClient(create_app()) as c:\n    assert c.post('/api/tasks', json={'title': 'Across processes'}).status_code == 201\n",
        "with TestClient(create_app()) as c:\n    assert c.get('/api/tasks').json()[0]['title'] == 'Across processes'\n",
    ]
    for script in scripts:
        subprocess.run([sys.executable, '-c', prefix + script], env=environment,
                       cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, text=True)
