from __future__ import annotations

from dataclasses import dataclass

from parts_multiagent.google_sheet_inventory import StockChangeItem


@dataclass(frozen=True)
class PeerStockInboundRequest:
    agent_name: str
    raw_items: str
    items: list[StockChangeItem]
