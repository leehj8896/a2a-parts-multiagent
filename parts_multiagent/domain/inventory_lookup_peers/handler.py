from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.agent_messages import EMPTY_QUERY_MESSAGE

from .types.request import PeerInventoryQueryRequest
from .types.response import PeerInventoryQueryResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


async def handle(
    agent: PartsMultiAgent,
    request: PeerInventoryQueryRequest,
) -> PeerInventoryQueryResponse:
    if not request.query:
        return PeerInventoryQueryResponse(
            status="error",
            message=EMPTY_QUERY_MESSAGE,
        )

    peer_errors = await agent.peers.refresh()
    result_text = await agent.query_peer_agents(request.query, peer_errors)

    return PeerInventoryQueryResponse(
        status="success",
        message=result_text,
    )
