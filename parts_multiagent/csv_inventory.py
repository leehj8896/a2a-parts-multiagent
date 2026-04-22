from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path

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
class CsvTable:
    path: Path
    frame: pd.DataFrame


class CsvInventory:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()

    def describe(self, tables: list[CsvTable] | None = None) -> str:
        if tables is None:
            tables = self._load_tables()
        if not tables:
            return f'No CSV files found in {self.data_dir}'
        lines = [f'Data directory: {self.data_dir}']
        for table in tables:
            columns = ', '.join(map(str, table.frame.columns))
            preview = table.frame.head(3).to_csv(index=False).strip()
            lines.append(
                f'- {table.path.name}: {len(table.frame)} rows; columns: {columns}\n'
                f'  preview:\n{preview}'
            )
        return '\n'.join(lines)

    def query(self, question: str) -> tuple[str, str]:
        tables = self._load_tables()
        context = self.describe(tables)
        if not tables:
            return context, f'{self.data_dir} 폴더에서 CSV 파일을 찾지 못했습니다.'

        terms = self._extract_terms(question)
        low_stock_threshold = self._extract_low_stock_threshold(question)
        wants_total = self._contains_any(
            question, ('총', '합계', '전체', 'total', 'sum')
        )

        sections = []
        for table in tables:
            df = table.frame.copy()
            name_cols = self._matching_columns(df, NAME_HINTS)
            qty_cols = self._matching_columns(df, QTY_HINTS)

            filtered = df
            used_terms = []
            if terms and name_cols:
                mask = pd.Series(False, index=df.index)
                for term in terms:
                    for col in name_cols:
                        mask |= df[col].astype(str).str.contains(
                            re.escape(term), case=False, na=False
                        )
                    if mask.any():
                        used_terms.append(term)
                if mask.any():
                    filtered = df[mask]

            if low_stock_threshold is not None and qty_cols:
                qty_col = qty_cols[0]
                numeric_qty = pd.to_numeric(filtered[qty_col], errors='coerce')
                filtered = filtered[numeric_qty < low_stock_threshold]

            if wants_total and qty_cols:
                qty_col = qty_cols[0]
                total = pd.to_numeric(
                    filtered[qty_col], errors='coerce'
                ).sum()
                sections.append(
                    f'[{table.path.name}] {qty_col} 합계: {total:g}'
                )

            if filtered.empty:
                sections.append(f'[{table.path.name}] 조건에 맞는 행이 없습니다.')
                continue

            preview = filtered.head(20).to_csv(index=False).strip()
            term_note = f" matched terms: {', '.join(used_terms)};" if used_terms else ''
            sections.append(
                f'[{table.path.name}]{term_note} {len(filtered)} matching rows'
                f'\n{preview}'
            )

        return context, '\n\n'.join(sections)

    def _load_tables(self) -> list[CsvTable]:
        if not self.data_dir.exists():
            return []
        tables = []
        for path in sorted(self.data_dir.glob('*.csv')):
            try:
                tables.append(CsvTable(path=path, frame=pd.read_csv(path)))
            except Exception as exc:
                error_frame = pd.DataFrame(
                    [{'file': path.name, 'error': str(exc)}]
                )
                tables.append(CsvTable(path=path, frame=error_frame))
        return tables

    def _extract_terms(self, question: str) -> list[str]:
        quoted = re.findall(r'["“”\']([^"“”\']+)["“”\']', question)
        tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9_.-]{1,}', question)
        korean_terms = re.findall(r'[가-힣A-Za-z0-9_.-]*(?:부품|품목|상품)[가-힣A-Za-z0-9_.-]*', question)
        terms = quoted + tokens + korean_terms
        stop = {
            'stock',
            'inventory',
            'total',
            'sum',
            'parts',
            'part',
            'csv',
        }
        return [term for term in dict.fromkeys(terms) if term.lower() not in stop]

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
