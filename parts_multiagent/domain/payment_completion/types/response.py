from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PaymentCompletionResponse:
    # "success" 또는 "error"
    status: str
    # 사람이 읽을 수 있는 메시지
    message: str
    # 처리된 주문번호
    order_id: str
    # 업데이트된 행 번호 (없으면 None)
    updated_row: int | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "order_id": self.order_id,
            "updated_row": self.updated_row,
        }
