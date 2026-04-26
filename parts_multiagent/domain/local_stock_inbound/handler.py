from __future__ import annotations

import json
import logging

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from parts_multiagent.constants.prefixes import INVENTORY_LOOKUP_LOCAL_PREFIX
from parts_multiagent.constants.structured_payload_keys import (
    ESTIMATED_DELIVERY_TIME,
    ITEMS,
    PART,
    QUANTITY,
    QUERY,
    SUMMARY_MESSAGE,
    SUPPLIER_AGENT,
    TOTAL_PRICE,
)
from parts_multiagent.domain.inventory.utils.inventory_log import (
    log_peer_agent_response,
)
from parts_multiagent.domain.inventory_lookup_local.constants.response_keys import (
    MATCHED_ROW_COUNT,
    MESSAGE,
    STATUS,
)
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    UNIT_PRICE,
)

from .types.request import StockInboundRequest
from .types.response import StockInboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


logger = logging.getLogger(__name__)
DEFAULT_ESTIMATED_DELIVERY_TIME = '배송시간 확인 필요'


@dataclass(frozen=True)
class OrderCandidateItem:
    requested_part: str
    part_code: str
    part_name: str
    quantity: int
    current_quantity: int
    unit_price: int | None
    total_price: int | None


# 주문 가능한 공급처 후보를 조회해 사용자 확인 메시지와 함께 반환합니다.
async def handle(
    agent: PartsMultiAgent,
    request: StockInboundRequest,
) -> StockInboundResponse:
    if not request.items:
        error_message = '주문할 품목과 수량을 입력해주세요.'
        return StockInboundResponse(
            status="error",
            error_message=error_message,
            message=error_message,
        )

    peer_errors = await agent.peers.refresh()
    request_text = f'{INVENTORY_LOOKUP_LOCAL_PREFIX} {request.raw_items}'
    candidate_by_agent = await _collect_order_candidates(
        agent,
        request,
        peer_errors,
        request_text,
    )
    order_candidates = [
        candidate_by_agent[peer_name]
        for peer_name in sorted(candidate_by_agent)
    ]
    if not order_candidates:
        error_message = _build_no_candidate_message(peer_errors)
        return StockInboundResponse(
            status="error",
            order_candidates=[],
            error_message=error_message,
            message=error_message,
        )

    confirmation_prompt = '주문하시겠습니까? 공급처를 선택해 주세요.'
    message = _build_candidate_message(
        order_candidates,
        confirmation_prompt,
        peer_errors,
    )
    return StockInboundResponse(
        status="success",
        order_candidates=order_candidates,
        confirmation_prompt=confirmation_prompt,
        message=message,
    )


# 피어별 재고 조회 결과를 모아 주문 가능한 공급처 후보를 구성합니다.
async def _collect_order_candidates(
    agent: PartsMultiAgent,
    request: StockInboundRequest,
    peer_errors: list[str],
    request_text: str,
) -> dict[str, dict[str, Any]]:
    candidate_by_agent: dict[str, dict[str, Any]] = {}
    for peer_name in agent.peers.agent_names():
        item_summaries = []
        candidate_items = []
        candidate_total_price = 0
        has_any_price = False
        can_supply_all_items = True
        for item in request.items:
            try:
                peer_result_text = await agent.peers.send_structured_message(
                    peer_name,
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                    {QUERY: item.part},
                    raw_response=True,
                )
            except Exception as exc:
                peer_errors.append(
                    f'{peer_name}: {type(exc).__name__}: {exc}'
                )
                can_supply_all_items = False
                break

            peer_result_dict = _parse_peer_result_dict(peer_result_text)
            peer_result_message = _peer_result_message(
                peer_result_dict,
                peer_result_text,
            )
            log_peer_agent_response(
                logger=logger,
                local_agent=agent.config.agent_name,
                source_agent=peer_name,
                request_text=request_text,
                response=peer_result_message,
            )
            extracted_order_item = _build_order_item_from_peer_result(
                item,
                peer_result_dict,
            )
            if extracted_order_item is None:
                can_supply_all_items = False
                break
            item_summaries.append(
                _build_item_summary_message(extracted_order_item)
            )
            candidate_items.append(
                _build_order_candidate_item_payload(extracted_order_item)
            )
            if extracted_order_item.unit_price is not None:
                has_any_price = True
            if extracted_order_item.total_price is not None:
                candidate_total_price += extracted_order_item.total_price

        if can_supply_all_items:
            estimated_delivery_time = _load_estimated_delivery_time(
                agent,
                peer_name,
            )
            candidate_by_agent[peer_name] = {
                SUPPLIER_AGENT: peer_name,
                ITEMS: candidate_items,
                ESTIMATED_DELIVERY_TIME: estimated_delivery_time,
                TOTAL_PRICE: candidate_total_price if has_any_price else None,
                SUMMARY_MESSAGE: _build_order_candidate_summary_message(
                    peer_name,
                    item_summaries,
                    candidate_total_price if has_any_price else None,
                    estimated_delivery_time,
                ),
            }
    return candidate_by_agent


# 피어 재고 조회 JSON 응답을 딕셔너리 형태로 정규화합니다.
def _parse_peer_result_dict(
    peer_result: str | dict[str, object],
) -> dict[str, object]:
    try:
        if isinstance(peer_result, str):
            parsed = json.loads(peer_result)
        else:
            parsed = peer_result
    except (json.JSONDecodeError, TypeError):
        parsed = {STATUS: "error", MESSAGE: peer_result}
    return parsed if isinstance(parsed, dict) else {STATUS: "error", MESSAGE: str(peer_result)}


# 피어 재고 조회 결과에서 사용자 표시용 메시지를 추출합니다.
def _peer_result_message(
    peer_result_dict: dict[str, object],
    peer_result_text: str,
) -> str:
    message = peer_result_dict.get(MESSAGE)
    if isinstance(message, str) and message:
        return message
    return peer_result_text if isinstance(peer_result_text, str) else str(peer_result_text)


# 피어 재고 조회 JSON 응답에서 주문 후보 품목 정보를 추출합니다.
def _build_order_item_from_peer_result(
    item,
    peer_result_dict: dict[str, object],
) -> OrderCandidateItem | None:
    if peer_result_dict.get(STATUS) != 'success':
        return None
    matched_row_count = peer_result_dict.get(MATCHED_ROW_COUNT)
    if not isinstance(matched_row_count, int) or matched_row_count <= 0:
        return None

    peer_result_message = peer_result_dict.get(MESSAGE)
    if not isinstance(peer_result_message, str) or not peer_result_message:
        return None

    extracted = _extract_match_from_message(peer_result_message, item.part)
    if extracted is None:
        return None
    part_code, part_name, current_quantity, unit_price = extracted
    if current_quantity < item.quantity:
        return None

    total_price = (
        unit_price * item.quantity if unit_price is not None else None
    )
    return OrderCandidateItem(
        requested_part=item.part,
        part_code=part_code,
        part_name=part_name,
        quantity=item.quantity,
        current_quantity=current_quantity,
        unit_price=unit_price,
        total_price=total_price,
    )


# 주문 후보 품목 정보를 구조화 payload item으로 변환합니다.
def _build_order_candidate_item_payload(
    order_candidate_item: 'OrderCandidateItem',
) -> dict[str, object]:
    item_payload = {
        PART: order_candidate_item.requested_part,
        QUANTITY: order_candidate_item.quantity,
    }
    if order_candidate_item.unit_price is not None:
        item_payload[UNIT_PRICE] = order_candidate_item.unit_price
    if order_candidate_item.total_price is not None:
        item_payload[TOTAL_PRICE] = order_candidate_item.total_price
    return item_payload


# 주문 후보 품목 정보를 사용자 표시용 문구로 조합합니다.
def _build_item_summary_message(
    order_candidate_item: 'OrderCandidateItem',
) -> str:
    if (
        order_candidate_item.part_name
        and order_candidate_item.part_name != order_candidate_item.part_code
    ):
        summary_message = (
            f'{order_candidate_item.part_code} '
            f'({order_candidate_item.part_name}) '
            f'{order_candidate_item.quantity}개 주문 가능'
            f' / 현재 재고 {order_candidate_item.current_quantity}개'
        )
    else:
        summary_message = (
            f'{order_candidate_item.part_code} '
            f'{order_candidate_item.quantity}개 주문 가능'
            f' / 현재 재고 {order_candidate_item.current_quantity}개'
        )

    if order_candidate_item.unit_price is None:
        return summary_message

    return (
        f'{summary_message} / 단가 {order_candidate_item.unit_price:,}원'
        f' / 총액 {order_candidate_item.total_price:,}원'
    )


# 공급처 이름으로 주문 후보에 노출할 배송 예상시간 문구를 조회합니다.
def _load_estimated_delivery_time(
    agent: PartsMultiAgent,
    supplier_agent_name: str,
) -> str:
    estimated_delivery_time_hours = (
        agent.config.supplier_delivery_time_by_agent.get(
            supplier_agent_name
        )
    )
    if estimated_delivery_time_hours is None:
        return DEFAULT_ESTIMATED_DELIVERY_TIME
    return _format_estimated_delivery_time_hours(
        estimated_delivery_time_hours
    )


# 시간 단위 배송 예정시간 정수를 사용자 노출용 문구로 변환합니다.
def _format_estimated_delivery_time_hours(
    estimated_delivery_time_hours: int,
) -> str:
    return f'{estimated_delivery_time_hours}시간'


# 주문 후보 요약 문구에 배송 예상시간을 함께 조합합니다.
def _build_order_candidate_summary_message(
    supplier_agent_name: str,
    item_summaries: list[str],
    candidate_total_price: int | None,
    estimated_delivery_time: str,
) -> str:
    delivery_summary = (
        estimated_delivery_time
        if estimated_delivery_time == DEFAULT_ESTIMATED_DELIVERY_TIME
        else f'배송 {estimated_delivery_time}'
    )
    total_price_summary = (
        f' / 후보 총액 {candidate_total_price:,}원'
        if candidate_total_price is not None
        else ''
    )
    return (
        f'[{supplier_agent_name}] '
        + ', '.join(item_summaries)
        + total_price_summary
        + f' / {delivery_summary}'
    )


# 재고 조회 메시지 CSV 블록에서 품목과 현재 재고를 추출합니다.
def _extract_match_from_message(
    peer_result_message: str,
    requested_part: str,
) -> tuple[str, str, int, int | None] | None:
    lines = [line.strip() for line in peer_result_message.splitlines() if line.strip()]
    for line in lines:
        if ',' not in line:
            continue
        columns = [column.strip() for column in line.split(',')]
        if len(columns) < 3:
            continue
        part_code, part_name, quantity_text = columns[:3]
        quantity = _parse_quantity(quantity_text)
        if quantity is None:
            continue
        unit_price = _parse_quantity(columns[3]) if len(columns) >= 4 else None
        if requested_part in {part_code, part_name}:
            return part_code, part_name, quantity, unit_price
        lowered_requested_part = requested_part.lower()
        if lowered_requested_part in part_code.lower() or lowered_requested_part in part_name.lower():
            return part_code, part_name, quantity, unit_price
    return None


# 수량 문자열을 정수로 안전하게 변환합니다.
def _parse_quantity(raw_quantity: str) -> int | None:
    normalized = raw_quantity.strip().replace(',', '')
    if not normalized:
        return None
    try:
        return int(float(normalized))
    except ValueError:
        return None


# 후보가 없을 때 피어 오류를 포함한 안내 메시지를 생성합니다.
def _build_no_candidate_message(peer_errors: list[str]) -> str:
    lines = ['주문 가능한 공급처를 찾지 못했습니다.']
    if peer_errors:
        lines.append('참고: 일부 peer agent 조회에 실패했습니다.')
        lines.extend(f'- {error}' for error in peer_errors)
    return '\n'.join(lines)


# 후보 공급처 목록과 확인 문구를 사용자 메시지로 구성합니다.
def _build_candidate_message(
    order_candidates: list[dict[str, Any]],
    confirmation_prompt: str,
    peer_errors: list[str],
) -> str:
    lines = ['주문 가능한 공급처 후보입니다.']
    for index, candidate in enumerate(order_candidates, start=1):
        summary_message = str(candidate.get(SUMMARY_MESSAGE, ''))
        lines.append(f'{index}. {summary_message}')
    lines.append(confirmation_prompt)
    if peer_errors:
        lines.append('참고: 일부 peer agent 조회에 실패했습니다.')
        lines.extend(f'- {error}' for error in peer_errors)
    return '\n'.join(lines)
