from __future__ import annotations

import json

from typing import TYPE_CHECKING

from parts_multiagent.constants.prefixes import PEER_STOCK_OUTBOUND_PREFIX
from parts_multiagent.constants.structured_payload_keys import (
    AGENT_NAME,
    ITEMS,
    RAW_ITEMS,
)
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    DETAILS,
    ITEMS_SHIPPED,
    MESSAGE,
    STATUS,
)
from parts_multiagent.domain.order_selection.constants.payment import (
    KAKAOPAY_PAYMENT_URL,
)
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

    message = (
        f'{request.supplier_agent} 공급처 주문이 접수되었습니다.\n'
        f'{peer_response.message}\n'
        '주문 상태: 결제대기\n'
        f'결제는 아래 URL에서 진행해주세요.\n'
        f'{KAKAOPAY_PAYMENT_URL}'
    )
    return OrderSelectionResponse(
        status='success',
        supplier_agent=request.supplier_agent,
        payment_url=KAKAOPAY_PAYMENT_URL,
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
    return OrderSelectionResponse(
        status=status,
        supplier_agent=supplier_agent,
        items_shipped=items_shipped if isinstance(items_shipped, int) else 0,
        message=message if isinstance(message, str) else '',
        details=details if isinstance(details, dict) else None,
    )
