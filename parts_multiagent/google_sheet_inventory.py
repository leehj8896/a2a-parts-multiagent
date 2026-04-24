from __future__ import annotations

import re

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd


UNSUPPORTED_LOCATION_HEADERS = ('location', '위치')
ORDER_HEADERS = [
    '기록시각',
    '에이전트',
    '구분',
    '품목',
    '수량',
    '변경전재고',
    '변경후재고',
    '금액',
    '요청내용',
    '상태',
]


@dataclass(frozen=True)
class GoogleSheetConfig:
    service_account_file: str
    spreadsheet_id: str
    inventory_worksheet: str
    order_worksheet: str
    inventory_headers: tuple[str, ...]


@dataclass(frozen=True)
class GoogleSheetTable:
    source: str
    frame: pd.DataFrame


@dataclass(frozen=True)
class StockChangeItem:
    part: str  # 부품명
    quantity: int  # 변경 수량
    unit_price: int | None = None  # 단위 가격
    part_code: str | None = None  # 부품 코드


@dataclass(frozen=True)
class StockCellUpdate:
    row: int
    col: int
    value: int


@dataclass(frozen=True)
class StockChange:
    part: str
    quantity: int
    before_stock: int
    after_stock: int
    row: int
    col: int
    is_new: bool = False
    unit_price: int | None = None
    write_unit_price: int | None = None
    price_col: int | None = None


@dataclass(frozen=True)
class NewInventoryRow:
    part: str  # 부품명
    quantity: int  # 초기 수량
    columns: list[str]  # 시트 열 목록
    name_col: str  # 부품명 열
    qty_col: str  # 수량 열
    unit_price: int | None = None  # 단위 가격
    part_code: str | None = None  # 부품 코드


class GoogleSheetInventory:
    def __init__(
        self,
        config: GoogleSheetConfig,
        values_loader: Callable[[], list[list[object]]] | None = None,
        stock_writer: Callable[[list[StockCellUpdate]], None] | None = None,
        order_appender: Callable[[list[list[object]]], None] | None = None,
        inventory_appender: Callable[[list[list[object]]], None] | None = None,
    ) -> None:
        self.config = config
        self._values_loader = values_loader
        self._stock_writer = stock_writer
        self._order_appender = order_appender
        self._inventory_appender = inventory_appender

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
        name_cols = list(self.config.inventory_headers[:2])
        qty_cols = [self.config.inventory_headers[2]]
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

    def change_stock(
        self,
        direction: str,
        items: list[StockChangeItem],
        request_text: str,
        agent_name: str,
    ) -> tuple[str, str]:
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
            return context, f'{table.source}에서 변경할 재고 행을 찾지 못했습니다.'
        if direction not in {'inbound', 'outbound'}:
            return context, f'지원하지 않는 재고 변경 구분입니다: {direction}'
        if not items:
            return context, '변경할 품목과 수량을 입력해주세요.'

        changes, new_rows, error = self._build_stock_changes(
            table, direction, items
        )
        if error is not None:
            return context, error

        stock_updates = []
        for change in changes:
            if change.is_new:
                continue
            stock_updates.append(
                StockCellUpdate(change.row, change.col, change.after_stock)
            )
            if (
                change.write_unit_price is not None
                and change.price_col is not None
            ):
                stock_updates.append(
                    StockCellUpdate(
                        change.row,
                        change.price_col,
                        change.write_unit_price,
                    )
                )
        inventory_rows = [
            self._build_new_inventory_row(nr) for nr in new_rows
        ]
        order_rows = [
            self._order_row(direction, request_text, agent_name, change)
            for change in changes
        ]

        try:
            if inventory_rows:
                self._append_inventory_rows(inventory_rows)
            self._write_stock_updates(stock_updates)
            self._append_order_rows(order_rows)
        except Exception as exc:
            return (
                context,
                f'Google Sheet를 업데이트하지 못했습니다: '
                f'{type(exc).__name__}: {exc}',
            )

        direction_label = '입고' if direction == 'inbound' else '출고'
        lines = [f'[{table.source}] {direction_label} 처리 완료: {len(changes)}건']
        total_amount = 0
        for change in changes:
            suffix = ' (신규)' if change.is_new else ''
            price_note = ''
            if change.unit_price is not None:
                amount = change.unit_price * change.quantity
                total_amount += amount
                price_note = f', 단가: {change.unit_price:,}원, 소계: {amount:,}원'
            lines.append(
                f'- {change.part}: {change.quantity}개 '
                f'({change.before_stock} -> {change.after_stock})'
                f'{price_note}{suffix}'
            )
        if total_amount > 0:
            lines.append(f'합계 금액: {total_amount:,}원')
        return context, '\n'.join(lines)

    def _load_table(self) -> GoogleSheetTable:
        values = (
            self._values_loader()
            if self._values_loader is not None
            else self._load_sheet_values()
        )
        frame = self._frame_from_values(values)
        self._validate_inventory_headers(frame)
        return GoogleSheetTable(source=self._source_description(), frame=frame)

    def _load_sheet_values(self) -> list[list[object]]:
        import gspread

        client = gspread.service_account(
            filename=self.config.service_account_file
        )
        spreadsheet = client.open_by_key(self.config.spreadsheet_id)
        worksheet = spreadsheet.worksheet(self.config.inventory_worksheet)
        return worksheet.get_all_values()

    def _write_stock_updates(self, updates: list[StockCellUpdate]) -> None:
        if self._stock_writer is not None:
            self._stock_writer(updates)
            return

        worksheet = self._open_inventory_worksheet()
        cells = [
            {
                'range': self._a1_cell(update.row, update.col),
                'values': [[update.value]],
            }
            for update in updates
        ]
        if cells:
            worksheet.batch_update(cells)

    def _append_inventory_rows(self, rows: list[list[object]]) -> None:
        if self._inventory_appender is not None:
            self._inventory_appender(rows)
            return

        worksheet = self._open_inventory_worksheet()
        if rows:
            worksheet.append_rows(rows)

    def _append_order_rows(self, rows: list[list[object]]) -> None:
        if self._order_appender is not None:
            self._order_appender(rows)
            return

        worksheet = self._open_order_worksheet()
        values = worksheet.get_all_values()
        if not values:
            worksheet.append_row(ORDER_HEADERS)
        if rows:
            worksheet.append_rows(rows)

    def _open_inventory_worksheet(self):
        spreadsheet = self._open_spreadsheet()
        return spreadsheet.worksheet(self.config.inventory_worksheet)

    def _open_order_worksheet(self):
        import gspread

        spreadsheet = self._open_spreadsheet()
        try:
            return spreadsheet.worksheet(self.config.order_worksheet)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(
                title=self.config.order_worksheet,
                rows=1000,
                cols=len(ORDER_HEADERS),
            )

    def _open_spreadsheet(self):
        import gspread

        client = gspread.service_account(
            filename=self.config.service_account_file
        )
        return client.open_by_key(self.config.spreadsheet_id)

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
        return f'{self.config.inventory_worksheet}'

    def _build_new_inventory_row(self, nr: NewInventoryRow) -> list[object]:
        row: list[object] = [''] * len(nr.columns)
        row[nr.columns.index(nr.name_col)] = nr.part
        row[nr.columns.index(nr.qty_col)] = nr.quantity
        if nr.part_code is not None:
            name_cols = list(self.config.inventory_headers[:2])
            if len(name_cols) >= 2:
                part_code_col = name_cols[0]
                row[nr.columns.index(part_code_col)] = nr.part_code
        price_col_index = self._price_column_index()
        if nr.unit_price is not None and price_col_index is not None:
            row[price_col_index] = nr.unit_price
        return row

    def _build_stock_changes(
        self,
        table: GoogleSheetTable,
        direction: str,
        items: list[StockChangeItem],
    ) -> tuple[list[StockChange], list[NewInventoryRow], str | None]:
        df = table.frame.copy()
        name_cols = list(self.config.inventory_headers[:2])
        qty_cols = [self.config.inventory_headers[2]]
        if not name_cols:
            return [], [], '품목을 찾을 수 있는 열이 없습니다.'
        if not qty_cols:
            return [], [], '재고 수량을 찾을 수 있는 열이 없습니다.'

        qty_col = qty_cols[0]
        qty_col_index = list(df.columns).index(qty_col) + 1
        columns = list(df.columns)
        price_col = None
        price_col_a1_index = None
        price_col_index = self._price_column_index()
        if price_col_index is not None and len(columns) > price_col_index:
            price_col = columns[price_col_index]
            price_col_a1_index = price_col_index + 1
        changes = []
        new_rows: list[NewInventoryRow] = []
        used_rows: set[int] = set()
        for item in items:
            if item.quantity <= 0:
                return [], [], f'{item.part} 수량은 1 이상이어야 합니다.'
            matched = self._matching_rows(df, name_cols, item.part)
            if len(matched) == 0:
                if direction == 'outbound':
                    return [], [], f'{item.part}에 맞는 품목을 찾지 못했습니다.'
                new_rows.append(NewInventoryRow(
                    part=item.part,
                    quantity=item.quantity,
                    columns=list(df.columns),
                    name_col=name_cols[1],
                    qty_col=qty_col,
                    unit_price=item.unit_price,
                    part_code=item.part_code,
                ))
                changes.append(StockChange(
                    part=item.part,
                    quantity=item.quantity,
                    before_stock=0,
                    after_stock=item.quantity,
                    row=0,
                    col=0,
                    is_new=True,
                    unit_price=item.unit_price,
                ))
                continue
            if len(matched) > 1:
                preview = df.loc[matched].head(5).to_csv(index=False).strip()
                return (
                    [],
                    [],
                    f'{item.part}에 여러 행이 매칭되어 변경하지 않았습니다.\n{preview}',
                )

            frame_index = int(matched[0])
            if frame_index in used_rows:
                return [], [], f'{item.part}가 요청 안에서 중복 매칭되었습니다.'
            used_rows.add(frame_index)
            current_stock = self._parse_stock(df.at[frame_index, qty_col])
            if current_stock is None:
                return [], [], f'{item.part}의 현재 재고가 숫자가 아닙니다.'

            unit_price = None
            if price_col is not None:
                unit_price = self._parse_stock(df.at[frame_index, price_col])

            write_unit_price = None
            if direction == 'outbound':
                if current_stock < item.quantity:
                    return (
                        [],
                        [],
                        f'{item.part} 출고 수량이 현재 재고보다 큽니다: '
                        f'{item.quantity} > {current_stock}',
                    )
                next_stock = current_stock - item.quantity
            else:
                if item.unit_price is not None:
                    unit_price = item.unit_price
                    if price_col_a1_index is not None:
                        write_unit_price = item.unit_price
                next_stock = current_stock + item.quantity

            changes.append(
                StockChange(
                    part=item.part,
                    quantity=item.quantity,
                    before_stock=current_stock,
                    after_stock=next_stock,
                    row=frame_index + 2,
                    col=qty_col_index,
                    unit_price=unit_price,
                    write_unit_price=write_unit_price,
                    price_col=price_col_a1_index,
                )
            )
        return changes, new_rows, None

    def _matching_rows(
        self,
        frame: pd.DataFrame,
        name_cols: list[str],
        part: str,
    ) -> list[int]:
        mask = pd.Series(False, index=frame.index)
        for col in name_cols:
            mask |= frame[col].astype(str).str.contains(
                re.escape(part),
                case=False,
                na=False,
            )
        return [int(index) for index in frame[mask].index]

    def _parse_stock(self, value: object) -> int | None:
        try:
            number = float(str(value).strip())
        except ValueError:
            return None
        if not number.is_integer():
            return None
        return int(number)

    def _order_row(
        self,
        direction: str,
        request_text: str,
        agent_name: str,
        change: StockChange,
    ) -> list[object]:
        amount: int | str = (
            change.unit_price * change.quantity
            if change.unit_price is not None
            else ''
        )
        return [
            datetime.now(timezone.utc).isoformat(),
            agent_name,
            '입고' if direction == 'inbound' else '출고',
            change.part,
            change.quantity,
            change.before_stock,
            change.after_stock,
            amount,
            request_text,
            '성공',
        ]

    def _a1_cell(self, row: int, col: int) -> str:
        name = ''
        while col:
            col, remainder = divmod(col - 1, 26)
            name = chr(ord('A') + remainder) + name
        return f'{name}{row}'

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

    def _contains_any(self, text: str, needles: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(needle.lower() in lowered for needle in needles)

    def _price_column_index(self) -> int | None:
        headers = list(self.config.inventory_headers)
        if len(headers) < 4:
            return None
        return 3

    def _validate_inventory_headers(self, frame: pd.DataFrame) -> None:
        columns = [str(column).strip() for column in frame.columns]
        if not columns:
            return
        expected = list(self.config.inventory_headers)
        lowered_columns = [column.lower() for column in columns]
        if any(
            marker.lower() in lowered_columns
            for marker in UNSUPPORTED_LOCATION_HEADERS
        ):
            raise ValueError(
                'inventory 워크시트에 위치(location/위치) 열은 지원하지 않습니다. '
                f'기대 헤더: {expected}; 현재 헤더: {columns}'
            )
        if len(columns) != len(expected):
            raise ValueError(
                'inventory 워크시트 헤더 열 개수가 올바르지 않습니다. '
                f'기대 헤더: {expected}; 현재 헤더: {columns}'
            )
        if columns != expected:
            raise ValueError(
                'inventory 워크시트 헤더 순서/이름이 올바르지 않습니다. '
                f'기대 헤더: {expected}; 현재 헤더: {columns}'
            )
