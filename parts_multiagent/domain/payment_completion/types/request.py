from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentCompletionRequest:
    # 결제가 완료된 주문번호
    order_id: str
    # 결제 완료를 처리할 대상 에이전트 이름(로컬 피어 처리에서는 비어있을 수 있음)
    target_agent: str | None = None
