import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


class Database:
    def __init__(self, url: str | None = None):
        url = make_url(url or os.getenv("DATABASE_URL", "sqlite:///./pairroom.db"))
        options = {}
        if url.get_backend_name() == "sqlite":
            options["connect_args"] = {"check_same_thread": False}
            if url.database in (None, "", ":memory:"):
                options["poolclass"] = StaticPool
        self.engine = create_engine(url, hide_parameters=True, **options)
        if url.get_backend_name() == "sqlite":
            event.listen(self.engine, "connect", self._sqlite_foreign_keys)
        self.sessions = sessionmaker(self.engine)

    @staticmethod
    def _sqlite_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def initialize(self):
        Base.metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()
