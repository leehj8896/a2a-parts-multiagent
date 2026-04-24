from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.agent_messages import EMPTY_QUERY_MESSAGE

from .request import PeerInventoryQueryRequest
from .response import PeerInventoryQueryResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


async def handle(
    agent: PartsMultiAgent,
    request: PeerInventoryQueryRequest,
) -> PeerInventoryQueryResponse:
    if not request.query:
        return PeerInventoryQueryResponse(EMPTY_QUERY_MESSAGE)
    peer_errors = await agent.peers.refresh()
    return PeerInventoryQueryResponse(
        await agent.query_peer_agents(request.query, peer_errors)
    )
