from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from parts_multiagent.domain.inventory_lookup_peers.constants.response_keys import (
    LOCAL_RESULT,
    MESSAGE,
    PEER_RESULTS,
    STATUS,
)


@dataclass(frozen=True)
class InventoryAgentQueryResult:
    """에이전트 재고 조회 요약 결과"""
    agent_name: str
    matched_row_count: int = 0
    message: str = ""


@dataclass(frozen=True)
class PeerInventoryLookupResult:
    """피어 재고 조회 결과"""
    agent_name: str
    status: str
    matched_row_count: int = 0
    message: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class PeerInventoryQueryResponse:
    """피어 전국 재고 조회 응답"""
    status: str  # "success" 또는 "error"
    local_result: InventoryAgentQueryResult | None = None
    peer_results: list[PeerInventoryLookupResult] = field(default_factory=list)
    message: str = ""

    def __str__(self) -> str:
        return self.message

    # 전국 재고 조회 응답을 JSON 직렬화 가능한 딕셔너리로 변환합니다.
    def to_json_dict(self) -> dict[str, Any]:
        return {
            STATUS: self.status,
            LOCAL_RESULT: (
                asdict(self.local_result) if self.local_result is not None else None
            ),
            PEER_RESULTS: [asdict(peer_result) for peer_result in self.peer_results],
            MESSAGE: self.message,
        }
