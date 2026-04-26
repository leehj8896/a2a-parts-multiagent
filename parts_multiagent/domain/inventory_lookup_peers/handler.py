from __future__ import annotations

import asyncio
import json
import logging

from typing import TYPE_CHECKING

from parts_multiagent.agent_messages import EMPTY_QUERY_MESSAGE
from parts_multiagent.constants.prefixes import INVENTORY_LOOKUP_LOCAL_PREFIX
from parts_multiagent.domain.inventory.utils.inventory_log import (
    log_inventory_response,
)
from parts_multiagent.domain.inventory_lookup_local.constants.response_keys import (
    MATCHED_ROW_COUNT as LOCAL_MATCHED_ROW_COUNT,
    MESSAGE as LOCAL_MESSAGE,
    STATUS as LOCAL_STATUS,
)
from parts_multiagent.utils.inventory_lookup_result import (
    extract_matched_row_count,
)
from parts_multiagent.utils.constants.structured_payload_keys import QUERY

from .types.request import PeerInventoryQueryRequest
from .types.response import (
    InventoryAgentQueryResult,
    PeerInventoryLookupResult,
    PeerInventoryQueryResponse,
)

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


logger = logging.getLogger(__name__)


# 로컬과 피어 agent 재고를 함께 조회해 구조화된 응답을 생성합니다.
async def handle(
    agent: PartsMultiAgent,
    request: PeerInventoryQueryRequest,
) -> PeerInventoryQueryResponse:
    if not request.query:
        return PeerInventoryQueryResponse(
            status="error",
            local_result=None,
            peer_results=[],
            message=EMPTY_QUERY_MESSAGE,
        )

    _, local_raw_result = agent.inventory.query(request.query)
    local_result = InventoryAgentQueryResult(
        agent_name=agent.config.agent_name,
        matched_row_count=extract_matched_row_count(local_raw_result),
        message=local_raw_result,
    )

    peer_errors = await agent.peers.refresh()
    peer_results = await _query_peer_inventory_results(agent, request.query)
    _log_inventory_lookup_results(
        local_agent=agent.config.agent_name,
        query=request.query,
        local_result=local_result,
        peer_results=peer_results,
    )
    result_text = _build_peer_inventory_message(
        local_result=local_result,
        peer_results=peer_results,
        peer_errors=peer_errors,
    )

    return PeerInventoryQueryResponse(
        status="success",
        local_result=local_result,
        peer_results=peer_results,
        message=result_text,
    )


# 피어 agent들에게 로컬 재고 조회 구조화 요청을 병렬 전송합니다.
async def _query_peer_inventory_results(
    agent: PartsMultiAgent,
    query: str,
) -> list[PeerInventoryLookupResult]:
    peer_names = agent.peers.agent_names()
    if not peer_names:
        return []

    peer_raw_results = await asyncio.gather(
        *[
            agent.peers.send_structured_message(
                peer_name,
                INVENTORY_LOOKUP_LOCAL_PREFIX,
                {QUERY: query},
                output_formats=["application/json"],
                raw_response=True,
            )
            for peer_name in peer_names
        ],
        return_exceptions=True,
    )

    peer_results: list[PeerInventoryLookupResult] = []
    for peer_name, peer_raw_result in zip(peer_names, peer_raw_results):
        peer_results.append(
            _parse_peer_inventory_lookup_result(peer_name, peer_raw_result)
        )
    return peer_results


# 피어의 구조화 응답을 전국 조회용 결과 타입으로 변환합니다.
def _parse_peer_inventory_lookup_result(
    peer_name: str,
    peer_raw_result: str | Exception,
) -> PeerInventoryLookupResult:
    if isinstance(peer_raw_result, Exception):
        error_message = (
            f"{type(peer_raw_result).__name__}: {peer_raw_result}"
        )
        return PeerInventoryLookupResult(
            agent_name=peer_name,
            status="error",
            matched_row_count=0,
            message=error_message,
            error_message=error_message,
        )

    try:
        response_data = json.loads(peer_raw_result)
    except json.JSONDecodeError:
        return PeerInventoryLookupResult(
            agent_name=peer_name,
            status="error",
            matched_row_count=0,
            message=peer_raw_result,
            error_message=peer_raw_result,
        )

    if not isinstance(response_data, dict):
        fallback_message = str(peer_raw_result)
        return PeerInventoryLookupResult(
            agent_name=peer_name,
            status="error",
            matched_row_count=0,
            message=fallback_message,
            error_message=fallback_message,
        )

    message = response_data.get(LOCAL_MESSAGE, "")
    message_text = message if isinstance(message, str) else str(peer_raw_result)
    matched_row_count = response_data.get(LOCAL_MATCHED_ROW_COUNT)
    if not isinstance(matched_row_count, int):
        matched_row_count = extract_matched_row_count(message_text)

    error_message = ""
    if response_data.get(LOCAL_STATUS) == "error":
        error_message = message_text

    return PeerInventoryLookupResult(
        agent_name=peer_name,
        status=str(response_data.get(LOCAL_STATUS, "error")),
        matched_row_count=matched_row_count,
        message=message_text,
        error_message=error_message,
    )


# 전국 재고 조회 결과를 사용자 표시용 메시지 문자열로 조합합니다.
def _build_peer_inventory_message(
    local_result: InventoryAgentQueryResult,
    peer_results: list[PeerInventoryLookupResult],
    peer_errors: list[str],
) -> str:
    sections = [
        f"## 내 재고 조회 ({local_result.agent_name})\n\n{local_result.message}"
    ]

    if peer_results:
        peer_sections = []
        for peer_result in peer_results:
            if peer_result.status == "error":
                peer_sections.append(
                    f"[{peer_result.agent_name}] 요청 실패: "
                    f"{peer_result.error_message or peer_result.message}"
                )
                continue
            peer_sections.append(
                f"[{peer_result.agent_name}] 응답입니다.\n\n{peer_result.message}"
            )
        sections.append("## 다른 agent 조회\n\n" + "\n\n".join(peer_sections))
    else:
        sections.append("## 다른 agent 조회\n\n조회 가능한 다른 agent가 없습니다.")

    if peer_errors:
        sections.append(
            "참고: 일부 peer agent의 AgentCard를 가져오지 못했습니다.\n"
            + "\n".join(f"- {error}" for error in peer_errors)
        )
    return "\n\n".join(sections)


# 전국 재고 조회 결과를 응답 생성과 별개로 source agent 색상 기준으로 기록합니다.
def _log_inventory_lookup_results(
    *,
    local_agent: str,
    query: str,
    local_result: InventoryAgentQueryResult,
    peer_results: list[PeerInventoryLookupResult],
) -> None:
    log_inventory_response(
        logger=logger,
        local_agent=local_agent,
        source_agent=local_result.agent_name,
        query=query,
        response=local_result.message,
    )
    for peer_result in peer_results:
        log_inventory_response(
            logger=logger,
            local_agent=local_agent,
            source_agent=peer_result.agent_name,
            query=query,
            response=peer_result.error_message or peer_result.message,
        )
