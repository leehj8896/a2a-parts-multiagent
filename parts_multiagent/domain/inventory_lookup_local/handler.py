from __future__ import annotations

from typing import TYPE_CHECKING

from parts_multiagent.agent_messages import EMPTY_QUERY_MESSAGE
from parts_multiagent.utils.inventory_lookup_result import (
    extract_matched_row_count,
)

from .types.request import LocalInventoryQueryRequest
from .types.response import LocalInventoryQueryResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


# 사용자 조회어로 로컬 재고를 조회하고 구조화된 응답을 생성합니다.
async def handle(
    agent: PartsMultiAgent,
    request: LocalInventoryQueryRequest,
) -> LocalInventoryQueryResponse:
    if not request.query:
        return LocalInventoryQueryResponse(
            status="error",
            matched_row_count=0,
            message=EMPTY_QUERY_MESSAGE,
        )

    _, raw_result = agent.inventory.query(request.query)

    return LocalInventoryQueryResponse(
        status="success",
        matched_row_count=extract_matched_row_count(raw_result),
        message=raw_result,
    )
