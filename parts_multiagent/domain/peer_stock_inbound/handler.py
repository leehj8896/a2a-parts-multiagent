from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.constants.prefixes import LOCAL_STOCK_INBOUND_PREFIX
from parts_multiagent.constants.structured_payload_keys import RAW_QUERY

from .types.request import PeerStockInboundRequest
from .types.response import PeerStockInboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


# 피어 agent의 로컬 입고 요청을 구조화 요청으로 위임합니다.
async def handle(
    agent: PartsMultiAgent,
    request: PeerStockInboundRequest,
) -> PeerStockInboundResponse:
    if request.agent_name not in agent.peers.agent_names():
        peer_errors = await agent.peers.refresh()
        if request.agent_name not in agent.peers.agent_names():
            errors = '\n'.join(f'- {error}' for error in peer_errors)
            suffix = f'\n{errors}' if errors else ''
            error_msg = f'요청 가능한 peer agent가 아닙니다: {request.agent_name}{suffix}'
            return PeerStockInboundResponse(
                status="error",
                message=error_msg,
            )
    
    inbound_payload = {RAW_QUERY: request.raw_items}
    result = await agent.peers.send_structured_message(
        request.agent_name,
        LOCAL_STOCK_INBOUND_PREFIX,
        inbound_payload,
        output_formats=["application/json"],
    )
    
    # 응답 파싱
    import json
    try:
        response_data = json.loads(result) if isinstance(result, str) else result
        is_error = response_data.get("status") == "error"
        items_received = response_data.get("data", {}).get("items_received", 0) if not is_error else 0
        message = response_data.get("message", result)
    except (json.JSONDecodeError, TypeError):
        is_error = True
        items_received = 0
        message = result
    
    return PeerStockInboundResponse(
        status="error" if is_error else "success",
        items_received=items_received,
        message=message,
    )
