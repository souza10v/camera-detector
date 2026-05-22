"""Sessão SQLAlchemy síncrona — usada exclusivamente pelo worker Celery."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

sync_engine = create_engine(settings.database_sync_url, pool_pre_ping=True, pool_size=5)
SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)
