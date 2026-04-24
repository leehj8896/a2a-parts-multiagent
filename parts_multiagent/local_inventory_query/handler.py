from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.agent_messages import EMPTY_QUERY_MESSAGE

from .request import LocalInventoryQueryRequest
from .response import LocalInventoryQueryResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


async def handle(
    agent: PartsMultiAgent,
    request: LocalInventoryQueryRequest,
) -> LocalInventoryQueryResponse:
    if not request.query:
        return LocalInventoryQueryResponse(EMPTY_QUERY_MESSAGE)
    return LocalInventoryQueryResponse(
        await agent.query_local(request.query, request.query)
    )
