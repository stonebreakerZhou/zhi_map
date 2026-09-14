"""Additive view metadata and operation-owned recovery, never a second history store."""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Table, Text

from .db import Base

positions = Table(
    "graph_positions", Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("branch_id", String, primary_key=True),
    Column("x", Float, nullable=False),
    Column("y", Float, nullable=False),
    Column("version", Integer, nullable=False),
)
contacts = Table(
    "graph_contacts", Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("source", String, primary_key=True),
    Column("target", String, primary_key=True),
)
operations = Table(
    "graph_removals", Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("id", String, primary_key=True),
    Column("committed", Integer, nullable=False),
    Column("expires", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("targets", Text, nullable=False),
    Column("data", Text, nullable=False),
)
