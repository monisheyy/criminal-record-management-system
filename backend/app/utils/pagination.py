"""Shared pagination/sorting helpers for list endpoints.

List endpoints keep returning a JSON array (backwards compatible) and expose
the total match count in the ``X-Total-Count`` response header so clients can
render server-side pagination.
"""
from typing import Dict, Optional

from fastapi import HTTPException, Response
from sqlalchemy.orm import Query

MAX_PAGE_SIZE = 200


def paginate(query: Query, response: Response, skip: int, limit: int):
    total = query.order_by(None).count()
    response.headers["X-Total-Count"] = str(total)
    return query.offset(skip).limit(limit).all()


def apply_sort(query: Query, sort: Optional[str], allowed: Dict[str, object], default):
    """Apply ``sort=field`` or ``sort=-field`` using an explicit column allowlist."""
    if not sort:
        return query.order_by(default)
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    column = allowed.get(key)
    if column is None:
        raise HTTPException(status_code=422, detail=f"Unsupported sort field. Allowed: {', '.join(sorted(allowed))}")
    return query.order_by(column.desc() if descending else column.asc())


def like_term(value: str) -> str:
    """Escape LIKE wildcards in user input so '%' and '_' match literally."""
    escaped = value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"
