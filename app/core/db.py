import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def engine_options(on_vercel: bool) -> dict:
    if not on_vercel:
        return {}
    # Vercel은 서버 인스턴스가 여럿 떴다 사라지므로 연결을 들고 있지 않고 풀러에 맡긴다.
    # Supabase transaction 풀러는 prepared statement를 지원하지 않는다
    return {"poolclass": NullPool, "connect_args": {"prepare_threshold": None}}


engine = create_engine(settings.database_url, **engine_options("VERCEL" in os.environ))
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as db:
        yield db
