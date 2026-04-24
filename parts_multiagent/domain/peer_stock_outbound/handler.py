from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .types.request import PeerStockOutboundRequest
from .types.response import PeerStockOutboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


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
    
    items_count, result = agent.inventory.change_stock(
        direction='outbound',
        items=request.items,
        request_text=request.raw_items,
        agent_name=request.agent_name,
    )
    
    # 성공 여부 판정
    is_error = any(
        marker in result
        for marker in (
            '조회하지 못했습니다',
            '변경할 재고 행을 찾지 못했습니다',
            '지원하지 않는 재고 변경 구분입니다',
            '변경할 품목과 수량을 입력해주세요',
            '업데이트하지 못했습니다',
        )
    )
    
    response = PeerStockOutboundResponse(
        status="error" if is_error else "success",
        items_shipped=items_count if not is_error else 0,
        message=result,
    )
    return response
