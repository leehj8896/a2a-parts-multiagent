from __future__ import annotations

import re

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd


NAME_HINTS = ('part', 'parts', 'item', 'sku', 'name', '품목', '부품', '상품')
QTY_HINTS = (
    'qty',
    'quantity',
    'stock',
    'inventory',
    'count',
    '수량',
    '재고',
)


@dataclass(frozen=True)
class GoogleSheetConfig:
    service_account_file: str
    spreadsheet_id: str
    worksheet: str


@dataclass(frozen=True)
class GoogleSheetTable:
    source: str
    frame: pd.DataFrame


class GoogleSheetInventory:
    def __init__(
        self,
        config: GoogleSheetConfig,
        values_loader: Callable[[], list[list[object]]] | None = None,
    ) -> None:
        self.config = config
        self._values_loader = values_loader

    def describe(self, table: GoogleSheetTable | None = None) -> str:
        if table is None:
            table = self._load_table()
        if table.frame.empty:
            return f'Google Sheet {table.source}에서 행을 찾지 못했습니다'
        columns = ', '.join(map(str, table.frame.columns))
        preview = table.frame.head(3).to_csv(index=False).strip()
        return (
            f'Google Sheet: {table.source}\n'
            f'- 행 수: {len(table.frame)}; 열: {columns}\n'
            f'  미리보기:\n{preview}'
        )

    def query(self, question: str) -> tuple[str, str]:
        try:
            table = self._load_table()
        except Exception as exc:
            context = self._source_description()
            return (
                context,
                f'Google Sheet를 조회하지 못했습니다: '
                f'{type(exc).__name__}: {exc}',
            )

        context = self.describe(table)
        if table.frame.empty:
            return context, f'{table.source}에서 조회할 재고 행을 찾지 못했습니다.'

        df = table.frame.copy()
        name_cols = self._matching_columns(df, NAME_HINTS)
        qty_cols = self._matching_columns(df, QTY_HINTS)
        terms = self._extract_terms(question)
        low_stock_threshold = self._extract_low_stock_threshold(question)
        wants_total = self._contains_any(
            question, ('총', '합계', '전체', 'total', 'sum')
        )

        filtered = df
        used_terms = []
        if terms and name_cols:
            mask = pd.Series(False, index=df.index)
            for term in terms:
                matched_term = False
                for col in name_cols:
                    term_mask = df[col].astype(str).str.contains(
                        re.escape(term), case=False, na=False
                    )
                    matched_term = matched_term or term_mask.any()
                    mask |= term_mask
                if matched_term:
                    used_terms.append(term)
            if mask.any():
                filtered = df[mask]

        sections = []
        if low_stock_threshold is not None and qty_cols:
            qty_col = qty_cols[0]
            numeric_qty = pd.to_numeric(filtered[qty_col], errors='coerce')
            filtered = filtered[numeric_qty < low_stock_threshold]

        if wants_total and qty_cols:
            qty_col = qty_cols[0]
            total = pd.to_numeric(filtered[qty_col], errors='coerce').sum()
            sections.append(f'[{table.source}] {qty_col} 합계: {total:g}')

        if filtered.empty:
            sections.append(f'[{table.source}] 조건에 맞는 행이 없습니다.')
            return context, '\n\n'.join(sections)

        preview = filtered.head(20).to_csv(index=False).strip()
        term_note = (
            f" 일치한 검색어: {', '.join(used_terms)};"
            if used_terms
            else ''
        )
        sections.append(
            f'[{table.source}]{term_note} 일치한 행 수: {len(filtered)}'
            f'\n{preview}'
        )
        return context, '\n\n'.join(sections)

    def _load_table(self) -> GoogleSheetTable:
        values = (
            self._values_loader()
            if self._values_loader is not None
            else self._load_sheet_values()
        )
        frame = self._frame_from_values(values)
        return GoogleSheetTable(source=self._source_description(), frame=frame)

    def _load_sheet_values(self) -> list[list[object]]:
        import gspread

        client = gspread.service_account(
            filename=self.config.service_account_file
        )
        spreadsheet = client.open_by_key(self.config.spreadsheet_id)
        worksheet = spreadsheet.worksheet(self.config.worksheet)
        return worksheet.get_all_values()

    def _frame_from_values(self, values: list[list[object]]) -> pd.DataFrame:
        rows = [
            [str(cell).strip() for cell in row]
            for row in values
            if any(str(cell).strip() for cell in row)
        ]
        if not rows:
            return pd.DataFrame()

        headers = [str(header).strip() for header in rows[0]]
        if not any(headers):
            return pd.DataFrame()

        width = len(headers)
        data_rows = []
        for row in rows[1:]:
            padded = [*row[:width], *([''] * max(width - len(row), 0))]
            data_rows.append(padded)
        return pd.DataFrame(data_rows, columns=headers)

    def _source_description(self) -> str:
        return (
            f'{self.config.spreadsheet_id}'
            f'/{self.config.worksheet}'
        )

    def _extract_terms(self, question: str) -> list[str]:
        quoted = re.findall(r'["“”\']([^"“”\']+)["“”\']', question)
        tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9_.-]{1,}', question)
        korean_terms = re.findall(
            r'[가-힣A-Za-z0-9_.-]*(?:부품|품목|상품)[가-힣A-Za-z0-9_.-]*',
            question,
        )
        terms = quoted + tokens + korean_terms
        stop = {
            'stock',
            'inventory',
            'total',
            'sum',
            'parts',
            'part',
            'sheet',
            'sheets',
        }
        return [
            term
            for term in dict.fromkeys(terms)
            if term.lower() not in stop
        ]

    def _extract_low_stock_threshold(self, question: str) -> int | None:
        if not self._contains_any(
            question, ('부족', '미만', '적은', 'low', 'below', 'less than')
        ):
            return None
        numbers = re.findall(r'\d+', question)
        if numbers:
            return int(numbers[0])
        return 10

    def _matching_columns(
        self, frame: pd.DataFrame, hints: tuple[str, ...]
    ) -> list[str]:
        matches = []
        for column in frame.columns:
            lowered = str(column).lower()
            if any(hint in lowered for hint in hints):
                matches.append(column)
        return matches

    def _contains_any(self, text: str, needles: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(needle.lower() in lowered for needle in needles)
