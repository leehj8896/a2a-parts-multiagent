from __future__ import annotations

from typing import Any

from parts_multiagent.constants.structured_payload_keys import (
    PART,
    QUANTITY,
)
from parts_multiagent.google_sheet_inventory import StockChangeItem


# StockChangeItem 목록을 structured payload(items) 배열로 변환합니다.
def stock_items_payload(items: list[StockChangeItem]) -> list[dict[str, Any]]:
    return [{PART: item.part, QUANTITY: item.quantity} for item in items]
