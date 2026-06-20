"""
Engine and session factory. Import get_session() wherever a DB session
is needed rather than constructing engines ad hoc.
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from app.config import DATABASE_URL

# check_same_thread=False is needed for SQLite when the app might touch
# the DB from more than one thread (e.g. a future web frontend); harmless
# for single-threaded CLI use.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Flask-Admin's SQLAlchemy backend expects a single long-lived Session it
# can use across several calls within one request (list query, then a
# separate save call, etc.) -- a different shape than get_session()'s
# one-off "open, use, commit, close" pattern used everywhere else in this
# app. This scoped_session gives Flask-Admin what it expects without
# changing that pattern for anything else; app/api/factory.py removes it
# at the end of every request via teardown_appcontext.
AdminScopedSession = scoped_session(SessionLocal)


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
