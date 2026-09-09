from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .database import TaskRow
from .models import Task, TaskCreate, TaskUpdate


def as_task(row):
    return Task(id=row.id, title=row.title, description=row.description, status=row.status)


class DatabaseTaskStore:
    def __init__(self, engine):
        self.sessions = sessionmaker(engine, expire_on_commit=False)

    def list(self) -> list[Task]:
        with self.sessions() as session:
            return [as_task(row) for row in session.scalars(select(TaskRow).order_by(TaskRow.id.desc()))]

    def create(self, values: TaskCreate) -> Task:
        with self.sessions.begin() as session:
            row = TaskRow(**values.model_dump())
            session.add(row)
            session.flush()
            result = as_task(row)
        return result

    def update(self, task_id: int, changes: TaskUpdate) -> Task:
        with self.sessions.begin() as session:
            row = session.get(TaskRow, task_id)
            if row is None:
                raise KeyError(task_id)
            for field, value in changes.model_dump(exclude_unset=True).items():
                setattr(row, field, value)
            session.flush()
            result = as_task(row)
        return result

    def delete(self, task_id: int) -> None:
        with self.sessions.begin() as session:
            row = session.get(TaskRow, task_id)
            if row is None:
                raise KeyError(task_id)
            session.delete(row)
