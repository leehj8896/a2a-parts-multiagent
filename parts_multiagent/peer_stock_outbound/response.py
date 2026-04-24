from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PeerStockOutboundResponse:
    text: str
