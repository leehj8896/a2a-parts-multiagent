from __future__ import annotations

import json

from typing import TYPE_CHECKING

from parts_multiagent.constants.prefixes import PEER_PAYMENT_COMPLETION_PREFIX
from parts_multiagent.constants.structured_payload_keys import ORDER_ID as PAYLOAD_ORDER_ID
from parts_multiagent.domain.payment_completion.constants.response_keys import (
    LOCAL_INVENTORY_APPENDED_COUNT,
    LOCAL_INVENTORY_UPDATED_COUNT,
    LOCAL_ORDER_UPDATED_COUNT,
    MESSAGE,
    ORDER_ID,
    STATUS,
    UPDATED_ROW,
)

from .types.request import PaymentCompletionRequest
from .types.response import PaymentCompletionResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


# 결제 완료 요청을 지정한 대상 에이전트의 피어 결제 완료 스킬로 전달합니다.
async def handle(
    agent: PartsMultiAgent,
    request: PaymentCompletionRequest,
) -> PaymentCompletionResponse:
    if not request.order_id or not request.order_id.strip():
        return PaymentCompletionResponse(
            status="error",
            message="주문번호가 제공되지 않았습니다.",
            order_id=request.order_id,
        )
    if not request.target_agent or not request.target_agent.strip():
        return PaymentCompletionResponse(
            status="error",
            message="결제 완료를 처리할 대상 에이전트 이름(supplier_agent)을 입력해주세요.",
            order_id=request.order_id,
        )

    try:
        peer_result = await agent.peers.send_structured_message(
            request.target_agent.strip(),
            PEER_PAYMENT_COMPLETION_PREFIX,
            {PAYLOAD_ORDER_ID: request.order_id.strip()},
            output_formats=["application/json"],
            raw_response=True,
        )
    except Exception as exc:
        return PaymentCompletionResponse(
            status="error",
            message=f"원격 결제 완료 요청에 실패했습니다: {type(exc).__name__}: {exc}",
            order_id=request.order_id,
        )
    peer_response = _parse_peer_payment_response(request.order_id.strip(), peer_result)
    if peer_response.status != "success":
        return peer_response

    (
        is_applied,
        apply_message,
        updated_inventory_count,
        appended_inventory_count,
        updated_order_count,
    ) = agent.inventory.apply_paid_inbound_order(
        peer_response.order_id,
        agent.config.agent_name,
    )
    if not is_applied:
        return PaymentCompletionResponse(
            status="error",
            message=apply_message,
            order_id=peer_response.order_id,
            updated_row=peer_response.updated_row,
            local_inventory_updated_count=0,
            local_inventory_appended_count=0,
            local_order_updated_count=0,
        )
    return PaymentCompletionResponse(
        status="success",
        message=f"{peer_response.message}\n{apply_message}",
        order_id=peer_response.order_id,
        updated_row=peer_response.updated_row,
        local_inventory_updated_count=updated_inventory_count,
        local_inventory_appended_count=appended_inventory_count,
        local_order_updated_count=updated_order_count,
    )


# 피어에서 전달받은 결제 완료 요청을 로컬 시트에만 반영합니다.
async def handle_local_only(
    agent: PartsMultiAgent,
    request: PaymentCompletionRequest,
) -> PaymentCompletionResponse:
    return _complete_local_payment(agent, request.order_id)


# 결제 완료 요청의 로컬 시트 반영을 수행하고 표준 응답 객체로 변환합니다.
def _complete_local_payment(
    agent: PartsMultiAgent,
    order_id: str,
) -> PaymentCompletionResponse:
    if not order_id or not order_id.strip():
        return PaymentCompletionResponse(
            status="error",
            message="주문번호가 제공되지 않았습니다.",
            order_id=order_id,
        )

    (
        is_applied,
        apply_message,
        updated_inventory_count,
        appended_inventory_count,
        updated_order_count,
    ) = agent.inventory.apply_paid_outbound_order(
        order_id.strip(),
        agent.config.agent_name,
    )
    if not is_applied:
        return PaymentCompletionResponse(
            status="error",
            message=apply_message,
            order_id=order_id.strip(),
            local_inventory_updated_count=0,
            local_inventory_appended_count=0,
            local_order_updated_count=0,
        )
    return PaymentCompletionResponse(
        status="success",
        message=apply_message,
        order_id=order_id.strip(),
        local_inventory_updated_count=updated_inventory_count,
        local_inventory_appended_count=appended_inventory_count,
        local_order_updated_count=updated_order_count,
    )


# 피어 결제 완료 응답(JSON 문자열/객체)을 PaymentCompletionResponse로 변환합니다.
def _parse_peer_payment_response(
    requested_order_id: str,
    peer_result: str | dict[str, object],
) -> PaymentCompletionResponse:
    try:
        payload = json.loads(peer_result) if isinstance(peer_result, str) else peer_result
    except (json.JSONDecodeError, TypeError):
        payload = None

    if not isinstance(payload, dict):
        return PaymentCompletionResponse(
            status="error",
            message="피어 결제 완료 응답을 해석하지 못했습니다.",
            order_id=requested_order_id,
        )

    response_status = payload.get(STATUS)
    response_message = payload.get(MESSAGE)
    response_order_id = payload.get(ORDER_ID)
    response_updated_row = payload.get(UPDATED_ROW)
    response_local_inventory_updated_count = payload.get(LOCAL_INVENTORY_UPDATED_COUNT)
    response_local_inventory_appended_count = payload.get(LOCAL_INVENTORY_APPENDED_COUNT)
    response_local_order_updated_count = payload.get(LOCAL_ORDER_UPDATED_COUNT)

    return PaymentCompletionResponse(
        status=response_status if isinstance(response_status, str) else "error",
        message=response_message if isinstance(response_message, str) else "",
        order_id=response_order_id if isinstance(response_order_id, str) else requested_order_id,
        updated_row=response_updated_row if isinstance(response_updated_row, int) else None,
        local_inventory_updated_count=(
            response_local_inventory_updated_count
            if isinstance(response_local_inventory_updated_count, int)
            else 0
        ),
        local_inventory_appended_count=(
            response_local_inventory_appended_count
            if isinstance(response_local_inventory_appended_count, int)
            else 0
        ),
        local_order_updated_count=(
            response_local_order_updated_count
            if isinstance(response_local_order_updated_count, int)
            else 0
        ),
    )
