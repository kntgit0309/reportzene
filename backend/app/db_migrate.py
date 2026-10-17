"""Add columns that exist in the models but not yet in the database (create_all only creates new tables).

Only additive, nullable columns: enough for this app's SQLite. Unique columns get a unique index.
"""
import logging

from sqlalchemy import Engine, inspect, text

from app.db import Base

log = logging.getLogger("rzn.migrate")


def add_missing_columns(engine: Engine) -> list[str]:
    added = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}'))
                if col.unique:
                    conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table.name}_{col.name}" ON "{table.name}" ("{col.name}")'))
                added.append(f"{table.name}.{col.name}")
                log.info("Added column %s.%s", table.name, col.name)
    return added
