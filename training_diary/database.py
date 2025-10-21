"""Database helpers for the training diary project."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, scoped_session, sessionmaker

from .config import get_settings


Base = declarative_base()

_engine = None
_session_factory: Optional[scoped_session[Session]] = None


def get_engine():
    """Return a lazily created SQLAlchemy engine."""

    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> scoped_session[Session]:
    """Return (and lazily create) the scoped session factory."""

    global _session_factory
    if _session_factory is None:
        _session_factory = scoped_session(
            sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)
        )
    return _session_factory


@contextmanager
def get_session():
    """Provide a transactional scope around a series of operations."""

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        get_session_factory().remove()


def init_db() -> None:
    """Create database tables if they do not exist."""

    from . import models  # noqa: F401 ensures models are imported

    Base.metadata.create_all(bind=get_engine())
