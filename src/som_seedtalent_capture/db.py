from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from som_seedtalent_capture.db_models import Base


def resolve_database_url(explicit_url: str | None = None) -> str | None:
    return explicit_url or os.environ.get("DATABASE_URL")


def build_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, connect_args=connect_args)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def build_session_factory(database_url: str | None = None):
    resolved = resolve_database_url(database_url)
    if resolved is None:
        return None
    engine = build_engine(resolved)
    initialize_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
