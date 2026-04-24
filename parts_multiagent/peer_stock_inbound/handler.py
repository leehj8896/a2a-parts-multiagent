from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.constants.prefixes import LOCAL_STOCK_INBOUND_PREFIX

from .request import PeerStockInboundRequest
from .response import PeerStockInboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


async def handle(
    agent: PartsMultiAgent,
    request: PeerStockInboundRequest,
) -> PeerStockInboundResponse:
    if request.agent_name not in agent.peers.agent_names():
        peer_errors = await agent.peers.refresh()
        if request.agent_name not in agent.peers.agent_names():
            errors = '\n'.join(f'- {error}' for error in peer_errors)
            suffix = f'\n{errors}' if errors else ''
            return PeerStockInboundResponse(
                f'요청 가능한 peer agent가 아닙니다: {request.agent_name}{suffix}'
            )
    result = await agent.peers.send_message(
        request.agent_name,
        f'{LOCAL_STOCK_INBOUND_PREFIX} {request.raw_items}',
    )
    return PeerStockInboundResponse(result)
