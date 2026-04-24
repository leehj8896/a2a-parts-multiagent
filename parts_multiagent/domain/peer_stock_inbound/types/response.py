from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PeerStockInboundResponse:
    """피어 재고 입고 요청 응답"""
    status: str  # "success" 또는 "error"
    items_received: int = 0
    message: str = ""

    def __str__(self) -> str:
        return self.message
    
    def to_json_dict(self) -> dict[str, Any]:
        """JSON으로 직렬화 가능한 딕셔너리 반환"""
        return {
            "status": self.status,
            "items_received": self.items_received,
            "message": self.message,
        }
