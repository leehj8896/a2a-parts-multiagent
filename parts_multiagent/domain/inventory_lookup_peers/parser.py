from __future__ import annotations

from .types.request import PeerInventoryQueryRequest


def parse(payload: str) -> PeerInventoryQueryRequest:
    return PeerInventoryQueryRequest(query=payload.strip())
