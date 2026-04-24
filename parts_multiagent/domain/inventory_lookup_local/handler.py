from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.agent_messages import EMPTY_QUERY_MESSAGE

from .types.request import LocalInventoryQueryRequest
from .types.response import LocalInventoryQueryResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


async def handle(
    agent: PartsMultiAgent,
    request: LocalInventoryQueryRequest,
) -> LocalInventoryQueryResponse:
    if not request.query:
        return LocalInventoryQueryResponse(
            status="error",
            message=EMPTY_QUERY_MESSAGE,
        )

    context, raw_result = agent.inventory.query(request.query)

    return LocalInventoryQueryResponse(
        status="success",
        message=raw_result,
    )
