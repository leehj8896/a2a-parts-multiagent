from __future__ import annotations

from typing import Any

from parts_multiagent.constants.skill_prefixes import (
    SKILL_INVENTORY_LOOKUP_LOCAL,
    SKILL_INVENTORY_LOOKUP_PEERS,
    SKILL_LOCAL_STOCK_INBOUND,
    SKILL_LOCAL_STOCK_OUTBOUND,
    SKILL_ORDER_SELECTION,
    SKILL_PAYMENT_COMPLETION,
    SKILL_PEER_STOCK_INBOUND,
    SKILL_PEER_STOCK_OUTBOUND,
)
from parts_multiagent.constants.structured_payload_keys import (
    AGENT_NAME,
    ITEMS,
    ORDER_ID,
    PART,
    QUERY,
    QUANTITY,
    RAW_ITEMS,
    SUPPLIER_AGENT,
    TARGET_AGENT,
)
from parts_multiagent.google_sheet_inventory import StockChangeItem
from parts_multiagent.local_inventory_query import LocalInventoryQueryRequest
from parts_multiagent.order_selection import OrderSelectionRequest
from parts_multiagent.payment_completion import PaymentCompletionRequest
from parts_multiagent.peer_inventory_query import PeerInventoryQueryRequest
from parts_multiagent.peer_stock_inbound import PeerStockInboundRequest
from parts_multiagent.peer_stock_outbound import PeerStockOutboundRequest
from parts_multiagent.stock_inbound import StockInboundRequest
from parts_multiagent.stock_outbound import StockOutboundRequest


def build_request_from_payload(skill_id: str, payload: dict[str, Any]) -> Any:
    if skill_id == SKILL_INVENTORY_LOOKUP_LOCAL:
        return LocalInventoryQueryRequest(query=_require_str(payload, QUERY))
    if skill_id == SKILL_INVENTORY_LOOKUP_PEERS:
        return PeerInventoryQueryRequest(query=_require_str(payload, QUERY))
    if skill_id == SKILL_LOCAL_STOCK_INBOUND:
        return _build_stock_inbound_request(payload)
    if skill_id == SKILL_ORDER_SELECTION:
        return _build_order_selection_request(payload)
    if skill_id == SKILL_LOCAL_STOCK_OUTBOUND:
        items, raw_items = _stock_items_and_raw(payload, require_items=True)
        return StockOutboundRequest(raw_items=raw_items, items=items)
    if skill_id == SKILL_PEER_STOCK_INBOUND:
        agent_name = _require_str(payload, AGENT_NAME)
        items, raw_items = _stock_items_and_raw(payload, require_items=True)
        return PeerStockInboundRequest(
            agent_name=agent_name,
            raw_items=raw_items,
            items=items,
        )
    if skill_id == SKILL_PEER_STOCK_OUTBOUND:
        agent_name = _require_str(payload, AGENT_NAME)
        items, raw_items = _stock_items_and_raw(payload, require_items=True)
        return PeerStockOutboundRequest(
            agent_name=agent_name,
            raw_items=raw_items,
            items=items,
        )
    if skill_id == SKILL_PAYMENT_COMPLETION:
        return PaymentCompletionRequest(order_id=_require_str(payload, ORDER_ID))
    raise ValueError(f'지원하지 않는 skill_id입니다: {skill_id}')


def _build_stock_inbound_request(payload: dict[str, Any]) -> StockInboundRequest:
    target_agent = _optional_str(payload, TARGET_AGENT)
    items, raw_items = _stock_items_and_raw(payload, require_items=True)
    return StockInboundRequest(
        target_agent=target_agent,
        raw_items=raw_items,
        items=items,
    )


def _build_order_selection_request(
    payload: dict[str, Any],
) -> OrderSelectionRequest:
    supplier_agent = _require_str(payload, SUPPLIER_AGENT)
    items, raw_items = _stock_items_and_raw(payload, require_items=True)
    return OrderSelectionRequest(
        supplier_agent=supplier_agent,
        raw_items=raw_items,
        items=items,
    )


def _stock_items_and_raw(
    payload: dict[str, Any],
    *,
    require_items: bool,
) -> tuple[list[StockChangeItem], str]:
    raw_items_value = _optional_str(payload, RAW_ITEMS)
    items_value = payload.get(ITEMS)

    items: list[StockChangeItem] = []
    if isinstance(items_value, list):
        items = _parse_stock_items(items_value)
    elif items_value is not None:
        raise ValueError(f'`{ITEMS}`는 배열이어야 합니다.')

    if require_items and not items:
        raise ValueError(f'`{ITEMS}`이(가) 비어 있습니다.')

    if raw_items_value:
        raw_items = raw_items_value
    else:
        raw_items = _format_stock_items(items)

    if require_items and not raw_items:
        raise ValueError(f'`{RAW_ITEMS}` 또는 `{ITEMS}`이(가) 필요합니다.')
    return items, raw_items


def _parse_stock_items(items_value: list[object]) -> list[StockChangeItem]:
    items: list[StockChangeItem] = []
    for idx, item_value in enumerate(items_value):
        if not isinstance(item_value, dict):
            raise ValueError(f'`{ITEMS}[{idx}]`는 객체여야 합니다.')
        part = _require_str(item_value, PART)
        quantity = _require_int(item_value, QUANTITY)
        if quantity <= 0:
            raise ValueError(f'`{ITEMS}[{idx}].{QUANTITY}`는 1 이상이어야 합니다.')
        items.append(StockChangeItem(part=part, quantity=quantity))
    return items


def _format_stock_items(items: list[StockChangeItem]) -> str:
    return ', '.join(f'{item.part} {item.quantity}' for item in items)


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'`{key}`는 비어있지 않은 문자열이어야 합니다.')
    return value.strip()


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'`{key}`는 문자열이어야 합니다.')
    stripped = value.strip()
    return stripped or None


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f'`{key}`는 정수여야 합니다.')
    return value
