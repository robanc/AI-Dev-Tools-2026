from typing import Annotated
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path, Response
from fastapi.middleware.cors import CORSMiddleware

from .models import Task, TaskCreate, TaskUpdate
from .store import DatabaseTaskStore
from .database import Base, database_url, make_engine


TaskId = Annotated[int, Path(ge=1)]


def create_app(url: str | None = None) -> FastAPI:
    # Connect only during startup, so importing the app never touches user data.
    @asynccontextmanager
    async def lifespan(app):
        nonlocal store
        engine = make_engine(url or database_url())
        try:
            Base.metadata.create_all(engine)
            store = DatabaseTaskStore(engine)
            yield
        finally:
            engine.dispose()

    store = None
    app = FastAPI(title='TaskLane API', version='0.1.0', lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            'http://localhost:5173', 'http://127.0.0.1:5173',
            'http://localhost:4173', 'http://127.0.0.1:4173',
        ],
        allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
        allow_headers=['Content-Type'],
    )

    @app.get('/api/tasks', response_model=list[Task], operation_id='listTasks')
    def list_tasks():
        return store.list()

    @app.post('/api/tasks', response_model=Task, status_code=201, operation_id='createTask')
    def create_task(values: TaskCreate):
        return store.create(values)

    @app.patch('/api/tasks/{id}', response_model=Task, operation_id='updateTask', responses={404: {'description': 'Task does not exist'}})
    def update_task(id: TaskId, changes: TaskUpdate):
        try:
            return store.update(id, changes)
        except KeyError:
            raise HTTPException(status_code=404, detail='Task not found.') from None

    @app.delete('/api/tasks/{id}', status_code=204, operation_id='deleteTask', responses={404: {'description': 'Task does not exist'}})
    def delete_task(id: TaskId):
        try:
            store.delete(id)
        except KeyError:
            raise HTTPException(status_code=404, detail='Task not found.') from None
        return Response(status_code=204)

    return app


app = create_app()
