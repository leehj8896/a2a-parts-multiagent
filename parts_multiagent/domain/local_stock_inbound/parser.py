from __future__ import annotations

from parts_multiagent.constants.stock_inbound_extraction import (
    STOCK_INBOUND_PARSE_ERROR,
)
from parts_multiagent.stock_items import parse_stock_items

from .types.request import StockInboundRequest


def parse(payload: str) -> StockInboundRequest:
    # 텍스트 주문 요청을 품목/수량 목록으로 해석합니다.
    payload = payload.strip()
    if not payload:
        raise ValueError(STOCK_INBOUND_PARSE_ERROR)
    try:
        items = parse_stock_items(payload)
    except ValueError as exc:
        raise ValueError(STOCK_INBOUND_PARSE_ERROR) from exc
    return StockInboundRequest(
        target_agent=None,
        raw_items=payload,
        items=items,
    )
