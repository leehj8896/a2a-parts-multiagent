from __future__ import annotations

from dataclasses import dataclass

from parts_multiagent.google_sheet_inventory import StockChangeItem


@dataclass(frozen=True)
class StockInboundRequest:
    target_agent: str | None
    raw_items: str
    items: list[StockChangeItem]
