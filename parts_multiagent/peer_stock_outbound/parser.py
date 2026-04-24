from __future__ import annotations

from parts_multiagent.stock_items import parse_stock_items

from .request import PeerStockOutboundRequest


def parse(payload: str) -> PeerStockOutboundRequest:
    payload = payload.strip()
    if not payload:
        raise ValueError('출고 요청을 보낼 agent 이름과 품목/수량을 입력해주세요.')
    agent_name, separator, raw_items = payload.partition(' ')
    if not separator or not agent_name.strip():
        raise ValueError('출고 요청을 보낼 agent 이름을 입력해주세요.')
    raw_items = raw_items.strip()
    return PeerStockOutboundRequest(
        agent_name=agent_name.strip(),
        raw_items=raw_items,
        items=parse_stock_items(raw_items),
    )
