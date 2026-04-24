from __future__ import annotations

from typing import TYPE_CHECKING

from .request import PeerStockOutboundRequest
from .response import PeerStockOutboundResponse

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
            return PeerStockOutboundResponse(
                f'요청 가능한 peer agent가 아닙니다: {request.agent_name}{suffix}'
            )
    _, result = agent.inventory.change_stock(
        direction='outbound',
        items=request.items,
        request_text=request.raw_items,
        agent_name=request.agent_name,
    )
    return PeerStockOutboundResponse(result)
