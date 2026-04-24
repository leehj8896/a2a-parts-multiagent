from __future__ import annotations

import re

from typing import TYPE_CHECKING

from parts_multiagent.constants.stock_inbound_extraction import (
    STOCK_INBOUND_LLM_FAILURE_PREFIX,
    STOCK_INBOUND_PARSE_ERROR,
)
from parts_multiagent.google_sheet_inventory import StockChangeItem
from parts_multiagent.constants.prefixes import (
    LOCAL_STOCK_INBOUND_PREFIX,
    PEER_STOCK_OUTBOUND_PREFIX,
)

from .request import StockInboundRequest
from .response import StockInboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


async def handle(
    agent: PartsMultiAgent,
    request: StockInboundRequest,
) -> StockInboundResponse:
    if request.needs_llm_extraction:
        peer_errors = await agent.peers.refresh()
        peer_agents = agent.peers.agent_summaries()
        try:
            extraction = await agent.llm.extract_stock_inbound(
                request.raw_query, peer_agents
            )
            canonical_request = _canonicalize_extraction(extraction)
        except Exception as exc:
            detail = f'{type(exc).__name__}: {exc}'
            return StockInboundResponse(
                f'{STOCK_INBOUND_PARSE_ERROR}\n'
                f'{STOCK_INBOUND_LLM_FAILURE_PREFIX}: {detail}'
            )
        request = canonical_request
    elif request.agent_name is None:
        return StockInboundResponse(STOCK_INBOUND_PARSE_ERROR)

    if request.agent_name not in agent.peers.agent_names():
        peer_errors = await agent.peers.refresh()
        if request.agent_name not in agent.peers.agent_names():
            errors = '\n'.join(f'- {error}' for error in peer_errors)
            suffix = f'\n{errors}' if errors else ''
            return StockInboundResponse(
                f'요청 가능한 peer agent가 아닙니다: '
                f'{request.agent_name}{suffix}'
            )
    try:
        peer_result = await agent.peers.send_message(
            request.agent_name,
            f'{PEER_STOCK_OUTBOUND_PREFIX} {agent.config.agent_name} '
            f'{request.raw_items}',
        )
    except Exception as exc:
        return StockInboundResponse(
            f'peer 출고 요청 실패: {request.agent_name}: '
            f'{type(exc).__name__}: {exc}'
        )

    priced_and_named_items = _apply_peer_metadata(request.items, peer_result)
    _, result = agent.inventory.change_stock(
        direction='inbound',
        items=priced_and_named_items,
        request_text=f'{LOCAL_STOCK_INBOUND_PREFIX} {request.agent_name} '
        f'{request.raw_items}',
        agent_name=agent.config.agent_name,
    )
    local_failed = any(
        marker in result
        for marker in (
            '조회하지 못했습니다',
            '변경할 재고 행을 찾지 못했습니다',
            '지원하지 않는 재고 변경 구분입니다',
            '변경할 품목과 수량을 입력해주세요',
            '업데이트하지 못했습니다',
        )
    )
    local_heading = (
        'peer 출고 성공, 로컬 업데이트 실패'
        if local_failed
        else '로컬 재고 데이터 업데이트 결과'
    )
    return StockInboundResponse(
        f'## peer 출고 결과 ({request.agent_name})\n\n{peer_result}\n\n'
        f'## {local_heading}\n\n{result}'
    )


def _canonicalize_extraction(extraction) -> StockInboundRequest:
    if not extraction.target_agent_name:
        raise ValueError(f'{extraction.reason or "agent를 특정하지 못했습니다."}')
    if not extraction.items:
        raise ValueError(f'{extraction.reason or "품목과 수량을 추출하지 못했습니다."}')

    items: list[StockChangeItem] = []
    raw_chunks: list[str] = []
    for item in extraction.items:
        part = item.part.strip()
        quantity = item.quantity
        if not part:
            raise ValueError('품목명이 비어 있습니다.')
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f'수량은 1 이상의 정수여야 합니다: {part}')
        items.append(StockChangeItem(part=part, quantity=quantity))
        raw_chunks.append(f'{part} {quantity}')

    return StockInboundRequest(
        agent_name=extraction.target_agent_name,
        raw_items=', '.join(raw_chunks),
        items=items,
        raw_query='',
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
