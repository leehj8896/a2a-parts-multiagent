from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentCompletionRequest:
    # 결제가 완료된 주문번호
    order_id: str
