from typing import Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

MAX_PER_PAGE = 200


class PageParams:
    def __init__(self, page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=MAX_PER_PAGE)):
        self.page, self.per_page = page, per_page


def paginate(db: Session, stmt: Select[Any], p: PageParams) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(p.per_page).offset((p.page - 1) * p.per_page)).unique().all()
    return list(rows), total
