"""Replace only untouched 0005 grid defaults; explicit position versions survive."""
from alembic import op

revision = "0006_forest_layout"
down_revision = "0005_constellation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""DELETE FROM graph_positions WHERE version=0 AND EXISTS (
      SELECT 1 FROM history_branches b WHERE b.user_id=graph_positions.user_id
      AND b.id=graph_positions.branch_id
      AND graph_positions.x=(b.position%64)*360
      AND graph_positions.y=CAST(b.position/64 AS INTEGER)*240)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_graph_parent_position
      ON history_branches(user_id,json_extract(data,'$.parent.branchId'),position)""")


def downgrade():
    op.drop_index("ix_graph_parent_position", "history_branches")
