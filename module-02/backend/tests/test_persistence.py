import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import Database
from app.main import create_app
from app.repository import SessionRepository
from app.store import PersistentStore
from conftest import authenticate, connect, headers


def test_restart_restores_grants_content_and_realtime(database_url):
    with TestClient(create_app()) as client:
        link = client.post('/sessions').json()['interviewerLink']
        session_id, owner = link.split('/')[2:]
        path = f'/sessions/{session_id}'
        access = client.get(path, headers=headers(owner)).json()
        candidate_link = access['candidateLink']
        candidate = candidate_link.split('/')[-1]
        empty = access['session']

    with TestClient(create_app(database_url=database_url)) as client:
        assert client.get(path, headers=headers(owner)).json()['session'] == empty
        for role, token in [('interviewer', owner), ('candidate', candidate)]:
            access = client.get(path, headers=headers(token)).json()
            assert access['role'] == role
            assert access['candidateLink'] == (candidate_link if role == 'interviewer' else None)
        assert client.put(path + '/problem', headers=headers(candidate), json={'problem': 'bad'}).status_code == 403
        assert client.get(path, headers=headers('wrong')).status_code == 404
        assert client.put(path + '/problem', headers=headers(owner), json={'problem': 'Sum\ntwo numbers'}).status_code == 200
        assert client.put(path + '/code', headers=headers(owner), json={'code': 'first'}).status_code == 200
        saved = client.put(path + '/code', headers=headers(candidate), json={'code': 'second'}).json()
        assert saved['revision'] == 3

    with TestClient(create_app(database_url=database_url)) as client:
        for token in [owner, candidate]:
            assert client.get(path, headers=headers(token)).json()['session'] == saved
            with connect(client, path) as socket:
                assert authenticate(socket, token) == {'type': 'snapshot', 'session': saved, 'otherConnected': False}
        assert saved['problem'] == 'Sum\ntwo numbers'
        assert saved['code'] == 'second'
        assert saved['createdAt'] == empty['createdAt']
        assert saved['updatedAt'].endswith('Z')
        with connect(client, path) as socket:
            assert authenticate(socket, 'wrong')['code'] == 'invalid_link'


def test_new_store_and_failed_commit(database_url):
    database = Database(database_url)
    database.initialize()
    session = PersistentStore(SessionRepository(database)).create()
    token = session.link('interviewer').split('/')[-1]

    async def exercise():
        queue = await session.subscribe('interviewer')
        queue.get_nowait()
        original = session.state

        def reject_commit(connection):
            raise RuntimeError('Simulated commit failure')

        event.listen(database.engine, 'commit', reject_commit)
        try:
            with pytest.raises(RuntimeError, match='Simulated commit failure'):
                await session.update('code', 'not saved')
        finally:
            event.remove(database.engine, 'commit', reject_commit)
        assert queue.empty()
        assert session.state == original
        saved = await session.update('problem', 'saved')
        assert queue.get_nowait()['session'] == saved.model_dump(mode='json')
        return saved

    try:
        saved = asyncio.run(exercise())
    finally:
        database.close()
    reopened = Database(database_url)
    try:
        restored, role = PersistentStore(SessionRepository(reopened)).authorize(session.id, token)
        assert role == 'interviewer'
        assert restored.state == saved
        assert restored.subscribers == {}
    finally:
        reopened.close()
