from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StockOutboundResponse:
    """출고 요청 응답"""
    status: str  # "success" 또는 "error"
    items_shipped: int = 0
    message: str = ""
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message
    
    def to_json_dict(self) -> dict[str, Any]:
        """JSON으로 직렬화 가능한 딕셔너리 반환"""
        result: dict[str, Any] = {
            "status": self.status,
            "items_shipped": self.items_shipped,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result
