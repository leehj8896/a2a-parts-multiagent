from __future__ import annotations

from .request import LocalInventoryQueryRequest


def parse(payload: str) -> LocalInventoryQueryRequest:
    return LocalInventoryQueryRequest(query=payload.strip())
