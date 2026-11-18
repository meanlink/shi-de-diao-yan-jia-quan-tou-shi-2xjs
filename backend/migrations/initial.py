from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models


# Columns added after the first release. CREATE TABLE IF NOT EXISTS will not add
# them to an existing database, so they are applied idempotently here.
_ADDED = {
    'jobs': [('volume_id', 'INTEGER REFERENCES volumes(id)'), ('idempotency_key', 'VARCHAR(64)')],
}


def migrate():
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in _ADDED.items():
            if table not in tables:
                continue
            existing = {c['name'] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in existing:
                    # SQLite cannot add a UNIQUE column in place; the index below covers both.
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        if 'jobs' in tables:
            connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_idempotency_key ON jobs (idempotency_key)'))
        if engine.dialect.name == 'postgresql':
            connection.execute(text('ALTER TABLE jobs ALTER COLUMN dataset_id DROP NOT NULL'))


if __name__ == '__main__':
    migrate()
