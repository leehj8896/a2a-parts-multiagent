from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.constants.structured_payload_keys import ITEMS, QUANTITY
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    PART_CODE,
    PART_NAME,
    REQUESTED_PART,
    UNIT_PRICE,
)

from .types.request import PeerStockOutboundRequest
from .types.response import PeerStockOutboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


# 피어 출고 요청은 실제 차감 대신 주문 접수만 기록하고 결제대기 상태로 응답합니다.
async def handle(
    agent: PartsMultiAgent,
    request: PeerStockOutboundRequest,
) -> PeerStockOutboundResponse:
    if (
        request.agent_name != agent.config.agent_name
        and request.agent_name not in agent.peers.agent_names()
    ):
        peer_errors = await agent.peers.refresh()
        if request.agent_name not in agent.peers.agent_names():
            errors = '\n'.join(f'- {error}' for error in peer_errors)
            suffix = f'\n{errors}' if errors else ''
            error_msg = f'요청 가능한 peer agent가 아닙니다: {request.agent_name}{suffix}'
            response = PeerStockOutboundResponse(
                status="error",
                message=error_msg,
            )
            return response
    
    item_details = _build_peer_outbound_details(agent, request)
    _, pending_order_message, order_id = agent.inventory.register_pending_outbound_order(
        items=request.items,
        request_text=request.raw_items,
        agent_name=request.agent_name,
    )
    is_error = pending_order_message.startswith('Google Sheet를') or any(
        error_marker in pending_order_message
        for error_marker in (
            '주문할 재고 행을 찾지 못했습니다',
            '주문할 품목과 수량을 입력해주세요.',
            '출고 수량이 현재 재고보다 큽니다',
            '맞는 품목을 찾지 못했습니다',
            '여러 행이 매칭되어 변경하지 않았습니다',
            '현재 재고가 숫자가 아닙니다',
            '수량은 1 이상이어야 합니다',
        )
    )

    response = PeerStockOutboundResponse(
        status="error" if is_error else "success",
        items_shipped=0,
        message=pending_order_message,
        details=item_details if not is_error else None,
        order_id=order_id if not is_error else "",
    )
    return response


# 출고 처리 전에 시트에서 품목 메타데이터를 조회해 피어 응답 상세에 담습니다.
def _build_peer_outbound_details(
    agent: PartsMultiAgent,
    request: PeerStockOutboundRequest,
) -> dict[str, object] | None:
    try:
        table = agent.inventory._load_table()
    except Exception:
        return None

    frame = table.frame.copy()
    if frame.empty:
        return None

    name_cols = agent.inventory.inventory_name_headers()
    if len(name_cols) < 2:
        return None

    price_col = agent.inventory.inventory_price_header()
    if price_col is not None and price_col not in frame.columns:
        price_col = None

    detail_items: list[dict[str, object]] = []
    for item in request.items:
        matched = agent.inventory._matching_rows(frame, name_cols, item.part)
        detail: dict[str, object] = {
            REQUESTED_PART: item.part,
            QUANTITY: item.quantity,
        }
        if len(matched) == 1:
            row = frame.loc[matched[0]]
            part_code = str(row[name_cols[0]]).strip()
            part_name = str(row[name_cols[1]]).strip()
            if part_code:
                detail[PART_CODE] = part_code
            if part_name:
                detail[PART_NAME] = part_name
            if price_col is not None:
                unit_price = agent.inventory._parse_stock(row[price_col])
                if unit_price is not None:
                    detail[UNIT_PRICE] = unit_price
        detail_items.append(detail)

    return {ITEMS: detail_items} if detail_items else None
