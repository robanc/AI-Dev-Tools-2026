from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    # Every test receives a separate on-disk database, never application data.
    with TestClient(create_app('sqlite:///' + (tmp_path / 'test.db').as_posix())) as client:
        yield client


def create(client, **values):
    response = client.post('/api/tasks', json={'title': 'Write report', **values})
    assert response.status_code == 201
    return response.json()


def test_empty_board(client):
    response = client.get('/api/tasks')
    assert response.status_code == 200
    assert response.json() == []


def test_create_defaults_and_newest_first(client):
    first = create(client, title='  First  ')
    second = create(client, title='Second', description='Full details\nSecond line')
    assert first == {'id': 1, 'title': 'First', 'description': '', 'status': 'todo'}
    assert second['id'] > first['id']
    assert client.get('/api/tasks').json() == [second, first]


def test_length_boundaries_and_trimming(client):
    task = create(client, title=' ' + 'x' * 200 + ' ', description='x' * 2000)
    assert task['title'] == 'x' * 200
    assert task['description'] == 'x' * 2000


@pytest.mark.parametrize('payload', [
    {}, {'title': ''}, {'title': ' \t\n '}, {'title': 'x' * 201},
    {'title': None}, {'title': 1}, {'title': True}, {'title': []},
    {'title': 'OK', 'description': 'x' * 2001},
    {'title': 'OK', 'description': None}, {'title': 'OK', 'description': 1},
    {'title': 'OK', 'status': 'done'}, {'title': 'OK', 'id': 99},
])
def test_invalid_creation_does_not_save(client, payload):
    response = client.post('/api/tasks', json=payload)
    assert response.status_code == 422
    assert response.json()['detail']
    assert client.get('/api/tasks').json() == []


def test_partial_edit_and_clear_description(client):
    task = create(client, description='Keep details')
    url = f"/api/tasks/{task['id']}"
    response = client.patch(url, json={'title': '  Edited  '})
    assert response.status_code == 200
    assert response.json() == {**task, 'title': 'Edited'}
    response = client.patch(url, json={'description': ''})
    assert response.json()['description'] == ''
    assert client.patch(url, json={}).json() == response.json()


def test_move_between_all_statuses(client):
    task = create(client, description='Keep details')
    for status in ['done', 'in_progress', 'todo']:
        response = client.patch(f"/api/tasks/{task['id']}", json={'status': status})
        assert response.status_code == 200
        assert response.json() == {**task, 'status': status}
        assert client.get('/api/tasks').json() == [response.json()]


@pytest.mark.parametrize('changes', [
    {'title': ''}, {'title': '  '}, {'title': 'x' * 201}, {'title': None},
    {'title': 1}, {'description': None}, {'description': 1},
    {'description': 'x' * 2001}, {'status': 'blocked'}, {'status': None},
    {'status': 1}, {'id': 10}, {'extra': 'field'},
    {'title': 'Valid change', 'status': 'invalid'},
])
def test_invalid_patch_is_atomic(client, changes):
    task = create(client)
    response = client.patch(f"/api/tasks/{task['id']}", json=changes)
    assert response.status_code == 422
    assert client.get('/api/tasks').json() == [task]


def test_delete_and_do_not_reuse_ids(client):
    task = create(client)
    response = client.delete(f"/api/tasks/{task['id']}")
    assert response.status_code == 204
    assert response.content == b''
    assert client.get('/api/tasks').json() == []
    assert create(client)['id'] > task['id']


@pytest.mark.parametrize('method', ['patch', 'delete'])
def test_missing_task(client, method):
    kwargs = {'json': {'title': 'Missing'}} if method == 'patch' else {}
    response = getattr(client, method)('/api/tasks/999', **kwargs)
    assert response.status_code == 404
    assert response.json() == {'detail': 'Task not found.'}


@pytest.mark.parametrize('task_id', ['abc', '0', '-1', '1.5'])
@pytest.mark.parametrize('method', ['patch', 'delete'])
def test_invalid_id(client, task_id, method):
    kwargs = {'json': {'title': 'Task'}} if method == 'patch' else {}
    assert getattr(client, method)(f'/api/tasks/{task_id}', **kwargs).status_code == 422


def test_malformed_json(client):
    assert client.post('/api/tasks', content='{', headers={'Content-Type': 'application/json'}).status_code == 422


def test_separate_databases_are_isolated(client, tmp_path):
    create(client)
    with TestClient(create_app('sqlite:///' + (tmp_path / 'other.db').as_posix())) as other:
        assert other.get('/api/tasks').json() == []
    assert len(client.get('/api/tasks').json()) == 1


@pytest.mark.parametrize('origin', [
    'http://127.0.0.1:5173', 'http://localhost:5173',
    'http://127.0.0.1:4173', 'http://localhost:4173',
])
def test_local_frontend_cors(client, origin):
    response = client.options('/api/tasks/1', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'PATCH',
        'Access-Control-Request-Headers': 'content-type',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == origin
    assert client.get('/api/tasks', headers={'Origin': origin}).headers['access-control-allow-origin'] == origin


def test_unlisted_origin_is_not_allowed(client):
    response = client.get('/api/tasks', headers={'Origin': 'https://example.com'})
    assert 'access-control-allow-origin' not in response.headers


def test_openapi_contract(client):
    contract = yaml.safe_load((Path(__file__).resolve().parents[2] / 'openapi.yaml').read_text())
    validate(contract)
    generated = client.get('/openapi.json').json()
    validate(generated)
    assert set(generated['paths']) == set(contract['paths'])
    for path, methods in contract['paths'].items():
        for method, operation in methods.items():
            if method == 'parameters':
                continue
            actual = generated['paths'][path][method]
            assert actual['operationId'] == operation['operationId']
            assert set(actual['responses']) == set(operation['responses'])
