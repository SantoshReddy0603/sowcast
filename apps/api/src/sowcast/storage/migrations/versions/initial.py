from sqlalchemy import Column, Float, String, Text, inspect

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    tables = set(inspect(connection).get_table_names())
    if "traces" not in tables:
        op.create_table(
            "traces",
            Column("id", String(36), primary_key=True),
            Column("body", Text, nullable=False),
            Column("saved", Float, nullable=False),
        )
    elif "saved" not in {c["name"] for c in inspect(connection).get_columns("traces")}:
        op.add_column("traces", Column("saved", Float, nullable=False, server_default="0"))
    if "backtest_results" not in tables:
        op.create_table(
            "backtest_results",
            Column("key", String(256), primary_key=True),
            Column("saved", Float, nullable=False),
            Column("body", Text, nullable=False),
        )
    if "backtest_jobs" not in tables:
        op.create_table(
            "backtest_jobs",
            Column("key", String(256), primary_key=True),
            Column("owner", String(36), nullable=False),
            Column("expires", Float, nullable=False),
        )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is not supported; restore a database backup")
