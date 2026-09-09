"""Minimal, dependency-free schema sync for SQLite.

`db.create_all()` only creates tables that don't exist yet - it never adds
columns to a table that's already there. Since this app has no Alembic/
Flask-Migrate setup, every model change that adds a column would otherwise
break existing installations with "no such column" errors on every request
that touches the table. This scans each mapped table for columns the model
declares but the database doesn't have yet, and adds them in place via
`ALTER TABLE ... ADD COLUMN`, which SQLite supports without rewriting the
table or touching existing rows.
"""
import sqlalchemy as sa


def _default_clause(engine, column: sa.Column) -> str:
    if column.default is not None and getattr(column.default, "is_scalar", False):
        value = column.default.arg
        if isinstance(value, bool):
            return f" DEFAULT {1 if value else 0}"
        if isinstance(value, (int, float)):
            return f" DEFAULT {value}"
        if isinstance(value, str):
            return f" DEFAULT '{value.replace(chr(39), chr(39) * 2)}'"

    if column.nullable:
        return ""

    # NOT NULL column with no usable scalar default (e.g. a callable like
    # datetime.utcnow): fall back to a type-appropriate literal so SQLite
    # can backfill existing rows.
    if isinstance(column.type, (sa.DateTime, sa.Date)):
        return " DEFAULT CURRENT_TIMESTAMP"
    if isinstance(column.type, (sa.Integer, sa.Numeric, sa.Float, sa.Boolean)):
        return " DEFAULT 0"
    return " DEFAULT ''"


def sync_schema(db):
    """Adds any model columns missing from the actual database tables."""
    engine = db.engine
    inspector = sa.inspect(engine)

    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue  # handled by create_all() already

        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue

            ddl_type = column.type.compile(dialect=engine.dialect)
            default_clause = _default_clause(engine, column)
            stmt = sa.text(
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                f"{ddl_type}{default_clause}"
            )
            with engine.begin() as conn:
                conn.execute(stmt)
