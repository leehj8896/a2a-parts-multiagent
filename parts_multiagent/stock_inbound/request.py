from __future__ import annotations

from dataclasses import dataclass

from parts_multiagent.google_sheet_inventory import StockChangeItem


@dataclass(frozen=True)
class StockInboundRequest:
    agent_name: str | None
    raw_items: str
    items: list[StockChangeItem]
    raw_query: str = ''

    @property
    def needs_llm_extraction(self) -> bool:
        return self.agent_name is None and not self.items and bool(self.raw_query)
