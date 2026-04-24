from __future__ import annotations

import json
import re

from typing import TYPE_CHECKING

from parts_multiagent.google_sheet_inventory import StockChangeItem
from parts_multiagent.constants.prefixes import (
    LOCAL_STOCK_INBOUND_PREFIX,
    PEER_STOCK_OUTBOUND_PREFIX,
)
from parts_multiagent.constants.structured_payload_keys import AGENT_NAME, ITEMS
from parts_multiagent.structured_payload import (
    stock_items_payload,
)

from .types.request import StockInboundRequest
from .types.response import StockInboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


# 로컬 입고 처리 시 피어 출고를 구조화 요청으로 호출한 뒤, 로컬 재고를 업데이트합니다.
async def handle(
    agent: PartsMultiAgent,
    request: StockInboundRequest,
) -> StockInboundResponse:
    if request.agent_name not in agent.peers.agent_names():
        peer_errors = await agent.peers.refresh()
        if request.agent_name not in agent.peers.agent_names():
            errors = '\n'.join(f'- {error}' for error in peer_errors)
            suffix = f'\n{errors}' if errors else ''
            error_msg = (
                f'요청 가능한 peer agent가 아닙니다: '
                f'{request.agent_name}{suffix}'
            )
            return StockInboundResponse(
                status="error",
                error_message=error_msg,
            )
    
    # 피어 출고 요청
    try:
        outbound_payload = {
            AGENT_NAME: agent.config.agent_name,
            ITEMS: stock_items_payload(request.items),
        }
        peer_result_text = await agent.peers.send_structured_message(
            request.agent_name,
            PEER_STOCK_OUTBOUND_PREFIX,
            outbound_payload,
            output_formats=["application/json"],
        )
    except Exception as exc:
        error_msg = (
            f'peer 출고 요청 실패: {request.agent_name}: '
            f'{type(exc).__name__}: {exc}'
        )
        return StockInboundResponse(
            status="error",
            error_message=error_msg,
        )

    # 피어 응답 파싱
    peer_result_dict = None
    try:
        if isinstance(peer_result_text, str):
            peer_result_dict = json.loads(peer_result_text)
        else:
            peer_result_dict = peer_result_text
    except (json.JSONDecodeError, TypeError):
        peer_result_dict = {"status": "error", "message": peer_result_text}

    priced_and_named_items = _apply_peer_metadata(request.items, peer_result_text)
    items_count, local_result = agent.inventory.change_stock(
        direction='inbound',
        items=priced_and_named_items,
        request_text=f'{LOCAL_STOCK_INBOUND_PREFIX} {request.agent_name} '
        f'{request.raw_items}',
        agent_name=agent.config.agent_name,
    )
    
    local_failed = any(
        marker in local_result
        for marker in (
            '조회하지 못했습니다',
            '변경할 재고 행을 찾지 못했습니다',
            '지원하지 않는 재고 변경 구분입니다',
            '변경할 품목과 수량을 입력해주세요',
            '업데이트하지 못했습니다',
        )
    )
    
    local_update_dict = {
        "status": "error" if local_failed else "success",
        "items_updated": items_count if not local_failed else 0,
        "message": local_result,
    }
    
    peer_section = f'## peer 출고 결과 ({request.agent_name})\n\n{peer_result_text}'
    local_section = f'## 로컬 재고 업데이트\n\n{local_result}'
    message = f'{peer_section}\n\n{local_section}'

    return StockInboundResponse(
        status="success" if not local_failed else "partial",
        peer_result=peer_result_dict,
        local_update=local_update_dict,
        message=message,
    )


def _apply_peer_metadata(
    items: list[StockChangeItem],
    peer_result: str,
) -> list[StockChangeItem]:
    prices_by_part = _extract_peer_unit_prices(peer_result)
    names_by_part = _extract_peer_part_names(peer_result)
    return [
        StockChangeItem(
            part=names_by_part.get(item.part, item.part),
            quantity=item.quantity,
            unit_price=prices_by_part.get(item.part),
            part_code=item.part if item.part in names_by_part else None,
        )
        for item in items
    ]


def _extract_peer_unit_prices(peer_result: str) -> dict[str, int]:
    prices: dict[str, int] = {}
    pattern = re.compile(
        r'^- (?P<part>.+?): \d+개 .*?단가: (?P<price>[\d,]+)원(?:,|$)',
        re.MULTILINE,
    )
    for match in pattern.finditer(peer_result):
        part = match.group('part').strip()
        price = int(match.group('price').replace(',', ''))
        prices[part] = price
    return prices


def _extract_peer_part_names(peer_result: str) -> dict[str, str]:
    names: dict[str, str] = {}
    pattern = re.compile(
        r'^- ([A-Za-z0-9_.-]+)\s+\(([^)]+)\):',
        re.MULTILINE,
    )
    for match in pattern.finditer(peer_result):
        part_code = match.group(1).strip()
        part_name = match.group(2).strip()
        names[part_code] = part_name
    return names
