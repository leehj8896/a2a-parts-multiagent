from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocalInventoryQueryResponse:
    """로컬 재고 조회 응답"""
    status: str  # "success" 또는 "error"
    items: list[dict[str, Any]] | None = None
    total_items: int = 0
    message: str = ""

    def __str__(self) -> str:
        return self.message
    
    def to_json_dict(self) -> dict[str, Any]:
        """JSON으로 직렬화 가능한 딕셔너리 반환"""
        return {
            "status": self.status,
            "items": self.items or [],
            "total_items": self.total_items,
            "message": self.message,
        }
