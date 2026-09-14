"""Strict native graph HTTP contracts, mounted by the existing application."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from .graph import GraphRepository
from .removals import RemovalRepository


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PositionInput(StrictModel):
    branchId: str = Field(min_length=1, max_length=200)
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)
    version: StrictInt = Field(ge=0)


class ContactInput(StrictModel):
    source: str = Field(min_length=1, max_length=200)
    targets: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=1, max_length=20)
    unlink: bool = False


class Target(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    revision: StrictInt = Field(ge=0)


class RemoveInput(StrictModel):
    operationId: str = Field(min_length=1, max_length=100)
    targets: list[Target] = Field(min_length=1, max_length=20)


class RestoreInput(StrictModel):
    asRoot: bool = False


def router(user, db):
    routes = APIRouter(prefix="/api/graph")

    @routes.get("/root/{branch_id}")
    def root(branch_id: str, uid=Depends(user), database: Session = Depends(db)):
        return GraphRepository(database, uid).root(branch_id)

    @routes.get("")
    def query(left: float = Query(-1000, ge=-1_000_000, le=1_000_000),
              top: float = Query(-1000, ge=-1_000_000, le=1_000_000),
              right: float = Query(2000, ge=-1_000_000, le=1_000_000),
              bottom: float = Query(2000, ge=-1_000_000, le=1_000_000),
              focus: str | None = Query(None, max_length=200),
              reading: str | None = Query(None, max_length=200),
              expand: str | None = Query(None, max_length=200),
              childCursor: int = Query(-1, ge=-1),
              search: str = Query("", max_length=120), cursor: int = Query(-1, ge=-1),
              uid=Depends(user), database: Session = Depends(db)):
        from .services import error
        if left > right or top > bottom:
            error(400, "视口边界无效。")
        return GraphRepository(database, uid).query([left, top, right, bottom], focus, search, cursor, reading, expand, childCursor)

    @routes.post("/positions")
    def move(input: PositionInput, uid=Depends(user), database: Session = Depends(db)):
        return GraphRepository(database, uid).position(input.branchId, input.x, input.y, input.version)

    @routes.post("/contacts")
    def contact(input: ContactInput, uid=Depends(user), database: Session = Depends(db)):
        return GraphRepository(database, uid).contact(input.source, input.targets, input.unlink)

    @routes.get("/removals")
    def recent(cursor: str = Query("", max_length=100), uid=Depends(user), database: Session = Depends(db)):
        return RemovalRepository(database, uid).recent(cursor)

    @routes.get("/removals/{operation_id}")
    def receipt(operation_id: str, uid=Depends(user), database: Session = Depends(db)):
        return RemovalRepository(database, uid).receipt(operation_id)

    @routes.post("/removals")
    async def remove(input: RemoveInput, uid=Depends(user), database: Session = Depends(db)):
        from .chat_stream import _removing, _runs, cancel
        keys = [(uid, t.id) for t in input.targets]
        _removing.update(keys)
        try:
            for key in keys:
                if key in _runs:
                    cancel(uid, key[1], _runs[key])
            return RemovalRepository(database, uid).remove(input.operationId, [t.model_dump() for t in input.targets])
        finally:
            _removing.difference_update(keys)

    @routes.post("/removals/{operation_id}/restore")
    async def restore(operation_id: str, input: RestoreInput, uid=Depends(user), database: Session = Depends(db)):
        return RemovalRepository(database, uid).restore(operation_id, input.asRoot)

    return routes
