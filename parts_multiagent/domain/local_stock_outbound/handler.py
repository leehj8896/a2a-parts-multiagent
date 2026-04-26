from __future__ import annotations

import re
from typing import TYPE_CHECKING

from parts_multiagent.constants.prefixes import LOCAL_STOCK_OUTBOUND_PREFIX
from parts_multiagent.google_sheet_inventory import GoogleSheetInventory

from .types.request import StockOutboundRequest
from .types.response import StockOutboundResponse

if TYPE_CHECKING:
    from parts_multiagent.agent import PartsMultiAgent


async def handle(
    agent: PartsMultiAgent,
    request: StockOutboundRequest,
) -> StockOutboundResponse:
    items_count, result = agent.inventory.change_stock(
        direction='outbound',
        items=request.items,
        request_text=f'{LOCAL_STOCK_OUTBOUND_PREFIX} {request.raw_items}',
        agent_name=agent.config.agent_name,
    )
    enriched_result = _enrich_with_part_names(result, agent.inventory)
    
    # 성공 여부 판정
    is_error = any(
        marker in enriched_result
        for marker in (
            '조회하지 못했습니다',
            '변경할 재고 행을 찾지 못했습니다',
            '지원하지 않는 재고 변경 구분입니다',
            '변경할 품목과 수량을 입력해주세요',
            '업데이트하지 못했습니다',
        )
    )
    
    return StockOutboundResponse(
        status="error" if is_error else "success",
        items_shipped=items_count if not is_error else 0,
        message=enriched_result,
    )


def _enrich_with_part_names(
    result: str, inventory: GoogleSheetInventory
) -> str:
    try:
        table = inventory._load_table()
    except Exception:
        return result

    df = table.frame.copy()
    name_cols = inventory.inventory_name_headers()
    if not name_cols or df.empty:
        return result

    part_names = {}
    for name_col in name_cols:
        if name_col in df.columns:
            for _, row in df.iterrows():
                part = str(row[name_col]).strip()
                if part and part not in part_names:
                    part_names[part] = name_col

    lines = []
    for line in result.split('\n'):
        match = re.match(r'^- (.+?): (\d+)개 ', line)
        if match and match.group(1) in part_names:
            part_code = match.group(1)
            part_name = _find_matching_part_name(df, name_cols, part_code)
            if part_name and part_name != part_code:
                line = line.replace(
                    f'- {part_code}:', f'- {part_code} ({part_name}):'
                )
        lines.append(line)
    return '\n'.join(lines)


def _find_matching_part_name(df, name_cols, part_code):
    for col in name_cols:
        if col in df.columns:
            matches = df[df[col].astype(str).str.contains(
                re.escape(part_code), case=False, na=False
            )]
            if not matches.empty:
                for other_col in name_cols:
                    if other_col != col and other_col in df.columns:
                        value = str(matches.iloc[0][other_col]).strip()
                        if value and value != part_code:
                            return value
    return None
