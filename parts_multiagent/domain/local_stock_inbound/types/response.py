from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parts_multiagent.constants.structured_payload_keys import (
    CONFIRMATION_PROMPT,
    ORDER_CANDIDATES,
)
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    MESSAGE,
    STATUS,
)


@dataclass(frozen=True)
class StockInboundResponse:
    """주문하기 (로컬 입고) 응답"""
    status: str  # "success" 또는 "error"
    order_candidates: list[dict[str, Any]] | None = None
    confirmation_prompt: str = ""
    error_message: str = ""
    message: str = ""

    def __str__(self) -> str:
        return self.message or self.error_message
    
    # 주문하기 응답을 JSON 직렬화 가능한 딕셔너리로 변환합니다.
    def to_json_dict(self) -> dict[str, Any]:
        return {
            STATUS: self.status,
            ORDER_CANDIDATES: self.order_candidates or [],
            CONFIRMATION_PROMPT: self.confirmation_prompt,
            "error_message": self.error_message,
            MESSAGE: self.message or self.error_message,
        }
