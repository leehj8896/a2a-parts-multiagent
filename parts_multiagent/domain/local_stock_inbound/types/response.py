from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class PeerOutboundResult:
    """출고 요청 결과 정보"""
    agent_name: str
    status: str  # "success" 또는 "error"
    items_shipped: int = 0
    message: str = ""


@dataclass(frozen=True)
class LocalUpdateResult:
    """로컬 재고 업데이트 결과 정보"""
    status: str  # "success" 또는 "error"
    items_updated: int = 0
    message: str = ""


@dataclass(frozen=True)
class StockInboundResponse:
    """주문하기 (로컬 입고) 응답"""
    status: str  # "success" 또는 "error"
    peer_result: dict[str, Any] | None = None
    local_update: dict[str, Any] | None = None
    error_message: str = ""
    message: str = ""

    def __str__(self) -> str:
        return self.message or self.error_message
    
    def to_json_dict(self) -> dict[str, Any]:
        """JSON으로 직렬화 가능한 딕셔너리 반환"""
        return {
            "status": self.status,
            "peer_result": self.peer_result,
            "local_update": self.local_update,
            "error_message": self.error_message,
        }
