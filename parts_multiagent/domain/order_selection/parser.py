from __future__ import annotations

from parts_multiagent.constants.stock_inbound_extraction import (
    STOCK_INBOUND_PARSE_ERROR,
)
from parts_multiagent.stock_items import parse_stock_items

from .types.request import OrderSelectionRequest


def parse(payload: str) -> OrderSelectionRequest:
    # 텍스트 주문선택 요청을 지원하지 않으므로 구조화 요청 사용을 안내합니다.
    payload = payload.strip()
    if not payload:
        raise ValueError(STOCK_INBOUND_PARSE_ERROR)
    try:
        items = parse_stock_items(payload)
    except ValueError as exc:
        raise ValueError(STOCK_INBOUND_PARSE_ERROR) from exc
    return OrderSelectionRequest(
        supplier_agent='',
        raw_items=payload,
        items=items,
    )
