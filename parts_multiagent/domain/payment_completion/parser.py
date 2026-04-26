from __future__ import annotations

import json

from parts_multiagent.constants.structured_payload_keys import ORDER_ID, SUPPLIER_AGENT

from .types.request import PaymentCompletionRequest


def parse(payload: str | dict) -> PaymentCompletionRequest:
    # 구조화된 JSON 요청을 PaymentCompletionRequest로 변환합니다.
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            raise ValueError("주문번호를 입력해주세요.")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {ORDER_ID: payload}
    else:
        data = payload

    if not isinstance(data, dict):
        raise ValueError("주문번호를 입력해주세요.")

    order_id = data.get(ORDER_ID, "").strip()
    target_agent = data.get(SUPPLIER_AGENT)
    normalized_target_agent = (
        target_agent.strip()
        if isinstance(target_agent, str) and target_agent.strip()
        else None
    )
    if not order_id:
        raise ValueError("주문번호를 입력해주세요.")

    return PaymentCompletionRequest(
        order_id=order_id,
        target_agent=normalized_target_agent,
    )
