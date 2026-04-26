from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    DETAILS,
    ITEMS_SHIPPED,
    MESSAGE,
    ORDER_ID,
    STATUS,
)


@dataclass(frozen=True)
class PeerStockOutboundResponse:
    """피어 출고 요청 응답"""
    status: str  # "success" 또는 "error"
    items_shipped: int = 0
    message: str = ""
    details: dict[str, Any] | None = None
    order_id: str = ""

    def __str__(self) -> str:
        return self.message

    # 피어 출고 응답을 JSON 직렬화 가능한 딕셔너리로 변환합니다.
    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            STATUS: self.status,
            ITEMS_SHIPPED: self.items_shipped,
            MESSAGE: self.message,
        }
        if self.details:
            result[DETAILS] = self.details
        if self.order_id:
            result[ORDER_ID] = self.order_id
        return result
