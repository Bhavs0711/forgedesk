from alembic import context
from sqlalchemy import create_engine

from forgedesk import models  # noqa: F401  (registers tables)
from forgedesk.db import Base

url = context.config.get_main_option("sqlalchemy.url")
engine = create_engine(url)
with engine.connect() as conn:
    context.configure(connection=conn, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
