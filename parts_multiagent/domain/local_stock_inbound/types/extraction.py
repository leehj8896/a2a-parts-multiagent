from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedStockItem:
    part: str
    quantity: int


@dataclass(frozen=True)
class StockInboundExtraction:
    target_agent_name: str | None
    items: list[ExtractedStockItem] = field(default_factory=list)
    reason: str = ''
