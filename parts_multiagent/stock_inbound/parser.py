from __future__ import annotations

from parts_multiagent.constants.stock_inbound_extraction import (
    STOCK_INBOUND_PARSE_ERROR,
)
from parts_multiagent.stock_items import parse_stock_items

from .request import StockInboundRequest


def parse(payload: str) -> StockInboundRequest:
    payload = payload.strip()
    if not payload:
        raise ValueError(STOCK_INBOUND_PARSE_ERROR)
    agent_name, separator, raw_items = payload.partition(' ')
    if not separator or not agent_name.strip():
        return StockInboundRequest(
            agent_name=None,
            raw_items='',
            items=[],
            raw_query=payload,
        )
    raw_items = raw_items.strip()
    try:
        items = parse_stock_items(raw_items)
    except ValueError as exc:
        if raw_items:
            return StockInboundRequest(
                agent_name=None,
                raw_items='',
                items=[],
                raw_query=payload,
            )
        raise ValueError(STOCK_INBOUND_PARSE_ERROR) from exc
    return StockInboundRequest(
        agent_name=agent_name.strip(),
        raw_items=raw_items,
        items=items,
    )
