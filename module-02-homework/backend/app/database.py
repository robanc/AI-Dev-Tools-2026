import os
from pathlib import Path

from sqlalchemy import String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = 'tasks'
    __table_args__ = {'sqlite_autoincrement': True}

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='todo')


def database_url():
    default = 'sqlite:///' + (Path(__file__).resolve().parents[1] / 'tasklane.db').as_posix()
    return os.environ.get('DATABASE_URL') or default


def make_engine(url):
    from sqlalchemy.engine import make_url
    options = {}
    if make_url(url).get_backend_name() == 'sqlite':
        options['connect_args'] = {'check_same_thread': False}
    return create_engine(url, **options)
