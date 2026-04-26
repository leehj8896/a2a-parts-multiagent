from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parts_multiagent.constants.structured_payload_keys import (
    ORDER_ID,
    PAYMENT_URL,
    SUPPLIER_AGENT,
)
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    DETAILS,
    ITEMS_SHIPPED,
    MESSAGE,
    STATUS,
)


@dataclass(frozen=True)
class OrderSelectionResponse:
    """주문선택 응답"""

    status: str
    supplier_agent: str
    payment_url: str = ""
    order_id: str = ""
    items_shipped: int = 0
    message: str = ""
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message

    # 주문선택 응답을 JSON 직렬화 가능한 딕셔너리로 변환합니다.
    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            STATUS: self.status,
            SUPPLIER_AGENT: self.supplier_agent,
            PAYMENT_URL: self.payment_url,
            ORDER_ID: self.order_id,
            ITEMS_SHIPPED: self.items_shipped,
            MESSAGE: self.message,
        }
        if self.details:
            result[DETAILS] = self.details
        return result
