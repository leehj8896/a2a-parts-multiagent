from __future__ import annotations

from .types.request import LocalInventoryQueryRequest


def parse(payload: str) -> LocalInventoryQueryRequest:
    return LocalInventoryQueryRequest(query=payload.strip())
