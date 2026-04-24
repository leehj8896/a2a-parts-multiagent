from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PeerInventoryQueryResponse:
    """피어 전국 재고 조회 응답"""
    status: str  # "success" 또는 "error"
    local_results: dict[str, Any] | None = None
    peer_results: dict[str, Any] | None = None
    message: str = ""

    def __str__(self) -> str:
        return self.message
    
    def to_json_dict(self) -> dict[str, Any]:
        """JSON으로 직렬화 가능한 딕셔너리 반환"""
        return {
            "status": self.status,
            "local_results": self.local_results,
            "peer_results": self.peer_results,
            "message": self.message,
        }
