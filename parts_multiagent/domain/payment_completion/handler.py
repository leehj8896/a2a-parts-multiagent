from __future__ import annotations

from typing import TYPE_CHECKING

from .types.request import PaymentCompletionRequest
from .types.response import PaymentCompletionResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


# 결제 완료 상태를 조회하여 주문 상태를 '결제대기'에서 '성공'으로 업데이트합니다.
async def handle(
    agent: PartsMultiAgent,
    request: PaymentCompletionRequest,
) -> PaymentCompletionResponse:
    if not request.order_id or not request.order_id.strip():
        return PaymentCompletionResponse(
            status="error",
            message="주문번호가 제공되지 않았습니다.",
            order_id=request.order_id,
        )

    try:
        updated_row = _update_order_status(agent, request.order_id)
        if updated_row is None:
            return PaymentCompletionResponse(
                status="error",
                message="주문번호를 찾을 수 없습니다.",
                order_id=request.order_id,
            )

        return PaymentCompletionResponse(
            status="success",
            message=f"주문 {request.order_id}의 결제가 완료되었습니다.",
            order_id=request.order_id,
            updated_row=updated_row,
        )
    except Exception as exc:
        return PaymentCompletionResponse(
            status="error",
            message=f"상태 업데이트에 실패했습니다: {type(exc).__name__}: {exc}",
            order_id=request.order_id,
        )


def _update_order_status(agent: PartsMultiAgent, order_id: str) -> int | None:
    # 주문 워크시트를 열어 order_id로 행을 찾고 상태를 업데이트합니다.
    import gspread

    spreadsheet = agent.inventory._open_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(agent.inventory.config.order_worksheet)
    except gspread.WorksheetNotFound:
        return None

    values = worksheet.get_all_values()
    if len(values) < 2:
        return None

    # 실제 시트의 헤더 행에서 컬럼 인덱스를 찾습니다 (config 헤더와 불일치 허용).
    actual_headers = values[0]
    try:
        order_id_col_index = actual_headers.index('주문번호')
        status_col_index = actual_headers.index('상태')
    except ValueError:
        return None

    # order_id와 일치하는 행 찾기
    target_row_index = None
    for i, row in enumerate(values[1:], start=2):  # 헤더 행 제외, 1-indexed
        if order_id_col_index < len(row) and row[order_id_col_index].strip() == order_id.strip():
            target_row_index = i
            break

    if target_row_index is None:
        return None

    # 현재 상태 확인
    row = values[target_row_index - 1]
    if status_col_index >= len(row):
        return None

    current_status = row[status_col_index].strip()
    if current_status == '성공':
        raise ValueError("이미 결제가 완료된 주문입니다.")

    # 상태 업데이트
    from parts_multiagent.domain.inventory.constants.gspread_batch_update_keys import (
        RANGE,
        VALUES,
    )

    status_cell = agent.inventory._a1_cell(target_row_index, status_col_index + 1)
    worksheet.batch_update(
        [
            {
                RANGE: status_cell,
                VALUES: [["성공"]],
            }
        ]
    )

    return target_row_index
