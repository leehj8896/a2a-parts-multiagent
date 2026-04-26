from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parts_multiagent.domain.payment_completion.constants.response_keys import (
    LOCAL_INVENTORY_APPENDED_COUNT,
    LOCAL_INVENTORY_UPDATED_COUNT,
    LOCAL_ORDER_UPDATED_COUNT,
    MESSAGE,
    ORDER_ID,
    STATUS,
    UPDATED_ROW,
)


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
    # 결제완료 후 로컬 inventory 업데이트 건수
    local_inventory_updated_count: int = 0
    # 결제완료 후 로컬 inventory 신규행 추가 건수
    local_inventory_appended_count: int = 0
    # 결제완료 후 로컬 order 상태 업데이트 건수
    local_order_updated_count: int = 0

    def to_json_dict(self) -> dict[str, Any]:
        return {
            STATUS: self.status,
            MESSAGE: self.message,
            ORDER_ID: self.order_id,
            UPDATED_ROW: self.updated_row,
            LOCAL_INVENTORY_UPDATED_COUNT: self.local_inventory_updated_count,
            LOCAL_INVENTORY_APPENDED_COUNT: self.local_inventory_appended_count,
            LOCAL_ORDER_UPDATED_COUNT: self.local_order_updated_count,
        }
