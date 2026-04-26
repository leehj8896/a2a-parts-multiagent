from __future__ import annotations

import json

from typing import TYPE_CHECKING

from parts_multiagent.constants.prefixes import PEER_STOCK_OUTBOUND_PREFIX
from parts_multiagent.constants.structured_payload_keys import (
    AGENT_NAME,
    ITEMS,
    ORDER_ID,
    QUANTITY,
    RAW_ITEMS,
)
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    DETAILS,
    ITEMS_SHIPPED,
    MESSAGE,
    PART_CODE,
    REQUESTED_PART,
    STATUS,
    UNIT_PRICE,
)
from parts_multiagent.domain.order_selection.constants.payment import (
    KAKAOPAY_PAYMENT_URL,
)
from parts_multiagent.google_sheet_inventory import StockChangeItem
from parts_multiagent.utils.structured_payload import stock_items_payload

from .types.request import OrderSelectionRequest
from .types.response import OrderSelectionResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


# 선택한 공급처로 피어 주문 접수를 요청하고 결제 URL을 포함한 응답을 반환합니다.
async def handle(
    agent: PartsMultiAgent,
    request: OrderSelectionRequest,
) -> OrderSelectionResponse:
    if not request.supplier_agent:
        error_message = '선택한 공급처를 입력해주세요.'
        return OrderSelectionResponse(
            status='error',
            supplier_agent='',
            message=error_message,
        )
    if not request.items:
        error_message = '주문할 품목과 수량을 입력해주세요.'
        return OrderSelectionResponse(
            status='error',
            supplier_agent=request.supplier_agent,
            message=error_message,
        )

    peer_response = await _request_peer_stock_outbound(agent, request)
    if peer_response.status != 'success':
        return OrderSelectionResponse(
            status='error',
            supplier_agent=request.supplier_agent,
            items_shipped=peer_response.items_shipped,
            message=peer_response.message,
            details=peer_response.details,
        )
    local_pending_items = _build_local_pending_inbound_items(
        request=request,
        peer_response=peer_response,
    )
    is_saved, local_message = agent.inventory.register_local_pending_inbound_order(
        order_id=peer_response.order_id,
        items=local_pending_items,
        request_text=request.raw_items,
        agent_name=request.supplier_agent,
    )
    if not is_saved:
        return OrderSelectionResponse(
            status='error',
            supplier_agent=request.supplier_agent,
            items_shipped=peer_response.items_shipped,
            message=local_message,
            details=peer_response.details,
        )

    message = (
        f'{request.supplier_agent} 공급처 주문이 접수되었습니다.\n'
        f'{peer_response.message}\n'
        f'{local_message}\n'
        f'주문번호: {peer_response.order_id}\n'
        '주문 상태: 결제대기\n'
        f'결제는 아래 URL에서 진행해주세요.\n'
        f'{KAKAOPAY_PAYMENT_URL}'
    )
    return OrderSelectionResponse(
        status='success',
        supplier_agent=request.supplier_agent,
        payment_url=KAKAOPAY_PAYMENT_URL,
        order_id=peer_response.order_id,
        items_shipped=peer_response.items_shipped,
        message=message,
        details=peer_response.details,
    )


# 주문선택 요청을 선택한 공급처 에이전트의 원격 출고 요청으로 변환합니다.
async def _request_peer_stock_outbound(
    agent: PartsMultiAgent,
    request: OrderSelectionRequest,
) -> OrderSelectionResponse:
    payload = {
        AGENT_NAME: request.supplier_agent,
        RAW_ITEMS: request.raw_items,
        ITEMS: stock_items_payload(request.items),
    }
    try:
        result = await agent.peers.send_structured_message(
            request.supplier_agent,
            PEER_STOCK_OUTBOUND_PREFIX,
            payload,
            output_formats=['application/json'],
            raw_response=True,
        )
    except Exception as exc:
        return OrderSelectionResponse(
            status='error',
            supplier_agent=request.supplier_agent,
            message=f'원격 출고 요청에 실패했습니다: {type(exc).__name__}: {exc}',
        )
    return _parse_peer_stock_outbound_response(
        supplier_agent=request.supplier_agent,
        result=result,
    )


# 피어 출고 JSON 응답을 주문선택 응답에서 재사용 가능한 형태로 정규화합니다.
def _parse_peer_stock_outbound_response(
    *,
    supplier_agent: str,
    result: str | dict[str, object],
) -> OrderSelectionResponse:
    try:
        response_data = json.loads(result) if isinstance(result, str) else result
    except (json.JSONDecodeError, TypeError):
        response_data = None

    if not isinstance(response_data, dict):
        return OrderSelectionResponse(
            status='error',
            supplier_agent=supplier_agent,
            message='원격 출고 응답을 해석하지 못했습니다.',
        )

    status = response_data.get(STATUS)
    if status not in {'success', 'error'}:
        return OrderSelectionResponse(
            status='error',
            supplier_agent=supplier_agent,
            message='원격 출고 응답 형식이 올바르지 않습니다.',
        )

    message = response_data.get(MESSAGE)
    items_shipped = response_data.get(ITEMS_SHIPPED)
    details = response_data.get(DETAILS)
    order_id = response_data.get(ORDER_ID)
    normalized_order_id = order_id.strip() if isinstance(order_id, str) else ''
    if status == 'success' and not normalized_order_id:
        return OrderSelectionResponse(
            status='error',
            supplier_agent=supplier_agent,
            message='원격 출고 응답 형식이 올바르지 않습니다: order_id가 없습니다.',
        )
    return OrderSelectionResponse(
        status=status,
        supplier_agent=supplier_agent,
        order_id=normalized_order_id,
        items_shipped=items_shipped if isinstance(items_shipped, int) else 0,
        message=message if isinstance(message, str) else '',
        details=details if isinstance(details, dict) else None,
    )


# 피어 출고 응답 상세(details) 기반으로 로컬 결제대기 입고 아이템 목록을 생성합니다.
def _build_local_pending_inbound_items(
    *,
    request: OrderSelectionRequest,
    peer_response: OrderSelectionResponse,
) -> list[StockChangeItem]:
    if not isinstance(peer_response.details, dict):
        return request.items

    raw_items = peer_response.details.get(ITEMS)
    if not isinstance(raw_items, list):
        return request.items

    detail_items: list[StockChangeItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        part_code = raw_item.get(PART_CODE)
        requested_part = raw_item.get(REQUESTED_PART)
        quantity = raw_item.get(QUANTITY)
        unit_price = raw_item.get(UNIT_PRICE)

        normalized_part_code = (
            part_code.strip()
            if isinstance(part_code, str) and part_code.strip()
            else None
        )
        normalized_requested_part = (
            requested_part.strip()
            if isinstance(requested_part, str) and requested_part.strip()
            else None
        )
        normalized_quantity = (
            quantity if isinstance(quantity, int) and quantity > 0 else None
        )
        normalized_unit_price = (
            unit_price if isinstance(unit_price, int) and unit_price >= 0 else None
        )
        part_for_inventory = normalized_part_code or normalized_requested_part
        if part_for_inventory is None or normalized_quantity is None:
            continue
        detail_items.append(
            StockChangeItem(
                part=part_for_inventory,
                quantity=normalized_quantity,
                unit_price=normalized_unit_price,
                part_code=normalized_part_code,
            )
        )
    if detail_items:
        return detail_items

    # 피어 상세가 비정상이면 사용자 입력 아이템으로 최소 동작을 보장합니다.
    fallback_items: list[StockChangeItem] = []
    for item in request.items:
        fallback_items.append(
            StockChangeItem(
                part=item.part,
                quantity=item.quantity,
                unit_price=item.unit_price,
                part_code=item.part if item.part else None,
            )
        )
    return fallback_items
