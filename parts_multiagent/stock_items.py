from __future__ import annotations

import re

from .google_sheet_inventory import StockChangeItem


def parse_stock_items(text: str) -> list[StockChangeItem]:
    items = []
    for chunk in text.split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.match(r'^(.+?)\s+(\d+)\s*(?:개|ea|pcs)?$', chunk)
        if match is None:
            raise ValueError(f'품목과 수량을 확인할 수 없습니다: {chunk}')
        part = match.group(1).strip()
        quantity = int(match.group(2))
        if not part:
            raise ValueError(f'품목을 입력해주세요: {chunk}')
        if quantity <= 0:
            raise ValueError(f'수량은 1 이상이어야 합니다: {chunk}')
        items.append(StockChangeItem(part=part, quantity=quantity))
    if not items:
        raise ValueError('변경할 품목과 수량을 입력해주세요.')
    return items
