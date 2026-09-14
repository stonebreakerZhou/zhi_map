"""Native constellation positions, typed contacts and independent removal receipts."""
from alembic import op
import sqlalchemy as sa

revision = "0005_constellation"
down_revision = "0004_delete_tombstones"
branch_labels = None
depends_on = None


def upgrade():
    from app.graph_schema import positions, contacts, operations
    for table in (positions, contacts, operations):
        table.create(op.get_bind(), checkfirst=True)
    op.execute(sa.text("INSERT OR IGNORE INTO graph_positions (user_id, branch_id, x, y, version) SELECT user_id, id, (position % 64) * 360, CAST(position / 64 AS INTEGER) * 240, 0 FROM history_branches"))
    op.create_index("ix_graph_removals_expiry", "graph_removals", ["user_id", "expires", "id"])
    op.execute(sa.text("CREATE INDEX ix_graph_parent ON history_branches (user_id, json_extract(data, '$.parent.branchId')) WHERE json_valid(data)"))
    op.execute(sa.text("CREATE INDEX ix_graph_reference ON history_entries (user_id, json_extract(data, '$.kind'), branch_id) WHERE json_valid(data)"))


def downgrade():
    op.drop_index("ix_graph_reference", "history_entries")
    op.drop_index("ix_graph_parent", "history_branches")
    op.drop_table("graph_removals")
    op.drop_table("graph_contacts")
    op.drop_table("graph_positions")
