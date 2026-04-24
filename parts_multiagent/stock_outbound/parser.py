from __future__ import annotations

from parts_multiagent.stock_items import parse_stock_items

from .request import StockOutboundRequest


def parse(payload: str) -> StockOutboundRequest:
    raw_items = payload.strip()
    if not raw_items:
        raise ValueError('출고할 품목과 수량을 입력해주세요.')
    return StockOutboundRequest(
        raw_items=raw_items,
        items=parse_stock_items(raw_items),
    )
