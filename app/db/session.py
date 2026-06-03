from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.paths import db_path, ensure_agent_dir
from app.core.exceptions import BootstrapError
from app.db.base import Base

# 返回数据库 URL
def database_url_for(target_path: Path) -> str:
    return f"sqlite:///{db_path(target_path)}"

# 创建会话工厂
def create_session_factory(target_path: Path) -> sessionmaker[Session]:
    ensure_agent_dir(target_path)
    engine = create_engine(database_url_for(target_path), future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)

# 打开现有会话工厂
def open_existing_session_factory(target_path: Path) -> sessionmaker[Session]:
    database_path = db_path(target_path)
    if not database_path.exists():
        raise BootstrapError("coding-agent database does not exist for this project")
    engine = create_engine(database_url_for(target_path), future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
