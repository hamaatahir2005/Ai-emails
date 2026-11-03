from alembic import context
from sqlalchemy import create_engine
from backend.app.config import config
from backend.app.db import Base
from backend.app import models

target_metadata = Base.metadata
if context.is_offline_mode():
    context.configure(url=config().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(config().database_url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
