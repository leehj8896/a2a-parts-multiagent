from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parts_multiagent.domain.inventory_lookup_local.constants.response_keys import (
    MATCHED_ROW_COUNT,
    MESSAGE,
    STATUS,
)


@dataclass(frozen=True)
class LocalInventoryQueryResponse:
    """로컬 재고 조회 응답"""
    status: str  # "success" 또는 "error"
    matched_row_count: int = 0
    message: str = ""

    def __str__(self) -> str:
        return self.message

    # 로컬 재고 조회 응답을 JSON 직렬화 가능한 딕셔너리로 변환합니다.
    def to_json_dict(self) -> dict[str, Any]:
        return {
            STATUS: self.status,
            MATCHED_ROW_COUNT: self.matched_row_count,
            MESSAGE: self.message,
        }
