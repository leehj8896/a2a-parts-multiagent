from __future__ import annotations

import re
import uuid

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from parts_multiagent.config import GoogleSheetSettings
from parts_multiagent.domain.inventory.constants.gspread_batch_update_keys import (
    RANGE,
    VALUES,
)
from parts_multiagent.domain.inventory.constants.order_statuses import (
    ORDER_STATUS_PAYMENT_PENDING,
    ORDER_STATUS_SUCCESS,
)
from parts_multiagent.domain.inventory.constants.order_worksheet_headers import (
    ORDER_DIRECTION_INBOUND,
    ORDER_DIRECTION_OUTBOUND,
    ORDER_HEADER_AFTER_STOCK,
    ORDER_HEADER_AGENT_NAME,
    ORDER_HEADER_BEFORE_STOCK,
    ORDER_HEADER_DIRECTION,
    ORDER_HEADER_ORDER_ID,
    ORDER_HEADER_PART_CODE,
    ORDER_HEADER_PRICE,
    ORDER_HEADER_QUANTITY,
    ORDER_HEADER_RECORDED_AT,
    ORDER_HEADER_REQUEST_TEXT,
    ORDER_HEADER_STATUS,
)

UNSUPPORTED_LOCATION_HEADERS = ('location', '위치')
GoogleSheetConfig = GoogleSheetSettings


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
    part_code: str | None
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
        order_values_loader: Callable[[], list[list[object]]] | None = None,
        order_status_writer: Callable[[list[dict[str, object]]], None] | None = None,
    ) -> None:
        self.config = config
        self._values_loader = values_loader
        self._stock_writer = stock_writer
        self._order_appender = order_appender
        self._inventory_appender = inventory_appender
        self._order_values_loader = order_values_loader
        self._order_status_writer = order_status_writer

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
        # 사용자 질의에서 검색 조건을 추출해 재고 행을 필터링합니다.
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
        name_cols = self.inventory_name_headers()
        qty_col = self.inventory_quantity_header()
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
            else:
                filtered = df.iloc[0:0]

        sections = []
        if low_stock_threshold is not None and qty_col is not None:
            numeric_qty = pd.to_numeric(filtered[qty_col], errors='coerce')
            filtered = filtered[numeric_qty < low_stock_threshold]

        if wants_total and qty_col is not None:
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

    # 피어 주문 접수 요청을 재고 차감 없이 주문 워크시트에만 기록합니다.
    def register_pending_outbound_order(
        self,
        items: list[StockChangeItem],
        request_text: str,
        agent_name: str,
    ) -> tuple[str, str, str]:
        try:
            table = self._load_table()
        except Exception as exc:
            context = self._source_description()
            return (
                context,
                f'Google Sheet를 조회하지 못했습니다: '
                f'{type(exc).__name__}: {exc}',
                '',
            )

        context = self.describe(table)
        if table.frame.empty:
            return context, f'{table.source}에서 주문할 재고 행을 찾지 못했습니다.', ''
        if not items:
            return context, '주문할 품목과 수량을 입력해주세요.', ''

        changes, _, error = self._build_stock_changes(
            table,
            'outbound',
            items,
        )
        if error is not None:
            return context, error, ''

        order_id = uuid.uuid4().hex[:10]
        order_rows = [
            self._order_row(
                direction='outbound',
                request_text=request_text,
                agent_name=agent_name,
                change=change,
                status=ORDER_STATUS_PAYMENT_PENDING,
                order_id=order_id,
            )
            for change in changes
        ]

        try:
            self._append_order_rows(order_rows)
        except Exception as exc:
            return (
                context,
                f'Google Sheet를 업데이트하지 못했습니다: '
                f'{type(exc).__name__}: {exc}',
                '',
            )

        lines = [f'[{table.source}] 주문 접수 완료: {len(changes)}건']
        total_amount = 0
        for change in changes:
            price_note = ''
            if change.unit_price is not None:
                amount = change.unit_price * change.quantity
                total_amount += amount
                price_note = f', 단가: {change.unit_price:,}원, 소계: {amount:,}원'
            lines.append(
                f'- {change.part}: {change.quantity}개 주문 접수'
                f' (현재 재고: {change.before_stock}개, 상태: {ORDER_STATUS_PAYMENT_PENDING})'
                f'{price_note}'
            )
        if total_amount > 0:
            lines.append(f'합계 금액: {total_amount:,}원')
        return context, '\n'.join(lines), order_id

    # 주문선택 성공 시 로컬 주문 워크시트에 결제대기(입고) 행을 저장합니다.
    def register_local_pending_inbound_order(
        self,
        order_id: str,
        items: list[StockChangeItem],
        request_text: str,
        agent_name: str,
    ) -> tuple[bool, str]:
        if not order_id or not order_id.strip():
            return False, '로컬 결제대기 주문 저장 실패: 주문번호가 비어있습니다.'

        try:
            table = self._load_table()
        except Exception as exc:
            return (
                False,
                f'로컬 결제대기 주문 저장 실패: '
                f'Google Sheet를 조회하지 못했습니다: {type(exc).__name__}: {exc}',
            )

        if table.frame.empty:
            return False, (
                f'로컬 결제대기 주문 저장 실패: '
                f'{table.source}에서 주문할 재고 행을 찾지 못했습니다.'
            )
        if not items:
            return False, '로컬 결제대기 주문 저장 실패: 주문할 품목과 수량을 입력해주세요.'

        changes, _, error = self._build_stock_changes(table, 'inbound', items)
        if error is not None:
            return False, f'로컬 결제대기 주문 저장 실패: {error}'

        order_rows = [
            self._order_row(
                direction='inbound',
                request_text=request_text,
                agent_name=agent_name,
                change=change,
                status=ORDER_STATUS_PAYMENT_PENDING,
                order_id=order_id.strip(),
            )
            for change in changes
        ]
        try:
            self._append_order_rows(order_rows)
        except Exception as exc:
            return (
                False,
                f'로컬 결제대기 주문 저장 실패: '
                f'Google Sheet를 업데이트하지 못했습니다: {type(exc).__name__}: {exc}',
            )
        return True, f'로컬 결제대기 주문 저장 완료: {len(order_rows)}건'

    # 결제완료 시 로컬 결제대기(입고) 주문을 찾아 재고 반영 후 상태를 성공으로 갱신합니다.
    def apply_paid_inbound_order(
        self,
        order_id: str,
        agent_name: str,
    ) -> tuple[bool, str, int, int, int]:
        return self._apply_paid_order_by_direction(
            order_id=order_id,
            agent_name=agent_name,
            order_direction=ORDER_DIRECTION_INBOUND,
            direction='inbound',
            direction_label='입고',
        )

    # 결제완료 시 로컬 결제대기(출고) 주문을 찾아 재고 차감 후 상태를 성공으로 갱신합니다.
    def apply_paid_outbound_order(
        self,
        order_id: str,
        agent_name: str,
    ) -> tuple[bool, str, int, int, int]:
        return self._apply_paid_order_by_direction(
            order_id=order_id,
            agent_name=agent_name,
            order_direction=ORDER_DIRECTION_OUTBOUND,
            direction='outbound',
            direction_label='출고',
        )

    # 결제 확정 시 주문 구분(입고/출고)에 맞춰 재고와 주문 상태를 함께 반영합니다.
    def _apply_paid_order_by_direction(
        self,
        *,
        order_id: str,
        agent_name: str,
        order_direction: str,
        direction: str,
        direction_label: str,
    ) -> tuple[bool, str, int, int, int]:
        try:
            table = self._load_table()
        except Exception as exc:
            return (
                False,
                f'로컬 결제 확정 반영 실패: Google Sheet를 조회하지 못했습니다: '
                f'{type(exc).__name__}: {exc}',
                0,
                0,
                0,
            )

        pending_items, target_rows, item_error = self._load_pending_order_items(
            order_id=order_id,
            order_direction=order_direction,
            direction_label=direction_label,
        )
        if item_error is not None:
            return False, f'로컬 결제 확정 반영 실패: {item_error}', 0, 0, 0

        changes, new_rows, stock_error = self._build_stock_changes(
            table,
            direction,
            pending_items,
        )
        if stock_error is not None:
            return False, f'로컬 결제 확정 반영 실패: {stock_error}', 0, 0, 0

        stock_updates = self._stock_updates_from_changes(changes)
        inventory_rows = (
            [self._build_new_inventory_row(row) for row in new_rows]
            if direction == 'inbound'
            else []
        )

        try:
            if inventory_rows:
                self._append_inventory_rows(inventory_rows)
            self._write_stock_updates(stock_updates)
            self._update_order_status_rows_to_success(target_rows)
        except Exception as exc:
            return (
                False,
                f'로컬 결제 확정 반영 실패: Google Sheet를 업데이트하지 못했습니다: '
                f'{type(exc).__name__}: {exc}',
                0,
                0,
                0,
            )

        updated_inventory_count = len(
            [change for change in changes if not change.is_new]
        )
        appended_inventory_count = len(inventory_rows)
        updated_order_count = len(target_rows)
        return (
            True,
            (
                f'로컬 결제 확정 반영 완료(에이전트: {agent_name}): '
                f'재고 업데이트 {updated_inventory_count}건, '
                f'재고 신규행 {appended_inventory_count}건, '
                f'주문상태 업데이트 {updated_order_count}건'
            ),
            updated_inventory_count,
            appended_inventory_count,
            updated_order_count,
        )

    # 계산된 재고 변경 목록을 시트 반영 단위(셀 업데이트 목록)로 변환합니다.
    def _stock_updates_from_changes(
        self,
        changes: list[StockChange],
    ) -> list[StockCellUpdate]:
        stock_updates: list[StockCellUpdate] = []
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
        return stock_updates

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
        # 재고 변경분을 Google Sheet에 batch_update로 반영합니다.
        if self._stock_writer is not None:
            self._stock_writer(updates)
            return

        worksheet = self._open_inventory_worksheet()
        cells = [
            {
                RANGE: self._a1_cell(update.row, update.col),
                VALUES: [[update.value]],
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

    # 주문 워크시트에 행을 추가하기 전에 헤더 정합성을 검증합니다.
    def _append_order_rows(self, rows: list[list[object]]) -> None:
        if self._order_appender is not None:
            self._order_appender(rows)
            return

        worksheet = self._open_order_worksheet()
        values = worksheet.get_all_values()
        if not values:
            worksheet.append_row(list(self.config.order_headers))
        else:
            self._validate_order_headers(values[0])
        if rows:
            worksheet.append_rows(rows)

    # 주문 워크시트 전체 값을 읽어옵니다.
    def _load_order_values(self) -> list[list[object]]:
        if self._order_values_loader is not None:
            return self._order_values_loader()
        worksheet = self._open_order_worksheet()
        return worksheet.get_all_values()

    # 주문 워크시트 상태 컬럼 업데이트를 배치로 반영합니다.
    def _write_order_status_updates(
        self,
        updates: list[dict[str, object]],
    ) -> None:
        if self._order_status_writer is not None:
            self._order_status_writer(updates)
            return
        worksheet = self._open_order_worksheet()
        if updates:
            worksheet.batch_update(updates)

    # 주문 워크시트 헤더가 설정과 동일한지 검증하고 누락/불일치를 명시적으로 실패시킵니다.
    def _validate_order_headers(self, headers: list[object]) -> None:
        expected_headers = list(self.config.order_headers)
        current_headers = [str(header).strip() for header in headers]
        if current_headers == expected_headers:
            return
        if ORDER_HEADER_ORDER_ID not in current_headers:
            raise ValueError(
                'order 워크시트 헤더에 주문번호 열이 없습니다. '
                f'기대 헤더: {expected_headers}; 현재 헤더: {current_headers}'
            )
        raise ValueError(
            'order 워크시트 헤더 순서/이름이 올바르지 않습니다. '
            f'기대 헤더: {expected_headers}; 현재 헤더: {current_headers}'
        )

    # 주문번호 기준 결제대기 입고 행을 조회해 재고 반영용 아이템과 대상 행번호를 반환합니다.
    def _load_pending_inbound_order_items(
        self,
        order_id: str,
    ) -> tuple[list[StockChangeItem], list[int], str | None]:
        return self._load_pending_order_items(
            order_id=order_id,
            order_direction=ORDER_DIRECTION_INBOUND,
            direction_label='입고',
        )

    # 주문번호 기준 결제대기 출고 행을 조회해 재고 반영용 아이템과 대상 행번호를 반환합니다.
    def _load_pending_outbound_order_items(
        self,
        order_id: str,
    ) -> tuple[list[StockChangeItem], list[int], str | None]:
        return self._load_pending_order_items(
            order_id=order_id,
            order_direction=ORDER_DIRECTION_OUTBOUND,
            direction_label='출고',
        )

    # 주문번호/구분 기준 결제대기 주문 행을 조회해 재고 반영용 아이템과 대상 행번호를 반환합니다.
    def _load_pending_order_items(
        self,
        *,
        order_id: str,
        order_direction: str,
        direction_label: str,
    ) -> tuple[list[StockChangeItem], list[int], str | None]:
        order_values = self._load_order_values()
        if len(order_values) < 2:
            return [], [], f'주문번호를 찾을 수 없습니다: {order_id}'

        headers = [str(value).strip() for value in order_values[0]]
        self._validate_order_headers(headers)
        header_index = {
            header: index for index, header in enumerate(headers)
        }
        required_headers = (
            ORDER_HEADER_ORDER_ID,
            ORDER_HEADER_DIRECTION,
            ORDER_HEADER_STATUS,
            ORDER_HEADER_PART_CODE,
            ORDER_HEADER_QUANTITY,
            ORDER_HEADER_PRICE,
        )
        missing_headers = [
            header
            for header in required_headers
            if header not in header_index
        ]
        if missing_headers:
            return [], [], (
                'order 워크시트 필수 헤더가 없습니다: '
                f'{", ".join(missing_headers)}'
            )

        target_rows: list[int] = []
        pending_items: list[StockChangeItem] = []
        for worksheet_row_index, row in enumerate(order_values[1:], start=2):
            row_order_id = self._row_cell_text(
                row,
                header_index[ORDER_HEADER_ORDER_ID],
            )
            if row_order_id != order_id.strip():
                continue
            row_direction = self._row_cell_text(
                row,
                header_index[ORDER_HEADER_DIRECTION],
            )
            row_status = self._row_cell_text(
                row,
                header_index[ORDER_HEADER_STATUS],
            )
            if (
                row_direction != order_direction
                or row_status != ORDER_STATUS_PAYMENT_PENDING
            ):
                continue

            part_code = self._row_cell_text(
                row,
                header_index[ORDER_HEADER_PART_CODE],
            )
            if not part_code:
                return [], [], '결제대기 주문 행에 부품번호가 없습니다.'
            quantity = self._parse_stock(
                self._row_cell_text(
                    row,
                    header_index[ORDER_HEADER_QUANTITY],
                )
            )
            if quantity is None or quantity <= 0:
                return [], [], '결제대기 주문 행의 수량이 올바르지 않습니다.'

            amount = self._parse_stock(
                self._row_cell_text(
                    row,
                    header_index[ORDER_HEADER_PRICE],
                )
            )
            unit_price = (
                amount // quantity
                if amount is not None and quantity > 0 and amount % quantity == 0
                else None
            )

            pending_items.append(
                StockChangeItem(
                    part=part_code,
                    quantity=quantity,
                    unit_price=unit_price,
                    part_code=part_code,
                )
            )
            target_rows.append(worksheet_row_index)

        if not pending_items:
            return [], [], (
                f'결제대기 {direction_label} 주문 행을 찾을 수 없습니다: {order_id}'
            )
        return pending_items, target_rows, None

    # 지정한 주문 워크시트 행들의 상태를 성공으로 일괄 갱신합니다.
    def _update_order_status_rows_to_success(self, row_indices: list[int]) -> None:
        if not row_indices:
            return
        order_values = self._load_order_values()
        if not order_values:
            return
        headers = [str(value).strip() for value in order_values[0]]
        self._validate_order_headers(headers)
        try:
            status_col_index = headers.index(ORDER_HEADER_STATUS) + 1
        except ValueError as exc:
            raise ValueError('order 워크시트에 상태 열이 없습니다.') from exc

        updates = [
            {
                RANGE: self._a1_cell(row_index, status_col_index),
                VALUES: [[ORDER_STATUS_SUCCESS]],
            }
            for row_index in row_indices
        ]
        self._write_order_status_updates(updates)

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
                cols=len(self.config.order_headers),
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

    # 부품재고 헤더 해석을 한 곳에서 관리합니다.
    def inventory_name_headers(self) -> list[str]:
        headers: list[str] = []
        part_code_header = self.inventory_part_code_header()
        if part_code_header is not None:
            headers.append(part_code_header)
        part_name_header = self.inventory_part_name_header()
        if part_name_header is not None:
            headers.append(part_name_header)
        return headers

    # 부품번호 열 이름을 설정에서 조회합니다.
    def inventory_part_code_header(self) -> str | None:
        return self._inventory_header_at(0)

    # 부품명 열 이름을 설정에서 조회합니다.
    def inventory_part_name_header(self) -> str | None:
        return self._inventory_header_at(1)

    # 수량 열 이름을 설정에서 조회합니다.
    def inventory_quantity_header(self) -> str | None:
        return self._inventory_header_at(2)

    # 가격 열 이름을 설정에서 조회합니다.
    def inventory_price_header(self) -> str | None:
        return self._inventory_header_at(3)

    # 부품재고 헤더 위치 접근을 공통화합니다.
    def _inventory_header_at(self, index: int) -> str | None:
        headers = list(self.config.inventory_headers)
        if len(headers) <= index:
            return None
        return headers[index]

    def _build_new_inventory_row(self, nr: NewInventoryRow) -> list[object]:
        row: list[object] = [''] * len(nr.columns)
        row[nr.columns.index(nr.name_col)] = nr.part
        row[nr.columns.index(nr.qty_col)] = nr.quantity
        if nr.part_code is not None:
            part_code_col = self.inventory_part_code_header()
            if part_code_col is not None:
                row[nr.columns.index(part_code_col)] = nr.part_code
        price_col = self.inventory_price_header()
        if nr.unit_price is not None and price_col is not None:
            row[nr.columns.index(price_col)] = nr.unit_price
        return row

    def _build_stock_changes(
        self,
        table: GoogleSheetTable,
        direction: str,
        items: list[StockChangeItem],
    ) -> tuple[list[StockChange], list[NewInventoryRow], str | None]:
        df = table.frame.copy()
        name_cols = self.inventory_name_headers()
        qty_col = self.inventory_quantity_header()
        if not name_cols:
            return [], [], '품목을 찾을 수 있는 열이 없습니다.'
        if qty_col is None:
            return [], [], '재고 수량을 찾을 수 있는 열이 없습니다.'

        qty_col_index = list(df.columns).index(qty_col) + 1
        columns = list(df.columns)
        price_col = self.inventory_price_header()
        price_col_a1_index = None
        if price_col is not None and price_col in columns:
            price_col_a1_index = columns.index(price_col) + 1
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
                part_name_col = self.inventory_part_name_header()
                if part_name_col is None:
                    return [], [], '부품명 열이 없어 신규 입고 행을 만들 수 없습니다.'
                new_rows.append(NewInventoryRow(
                    part=item.part,
                    quantity=item.quantity,
                    columns=list(df.columns),
                    name_col=part_name_col,
                    qty_col=qty_col,
                    unit_price=item.unit_price,
                    part_code=item.part_code,
                ))
                changes.append(StockChange(
                    part=item.part,
                    part_code=item.part_code,
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
                        self._build_outbound_quantity_exceeds_stock_message(
                            part=item.part,
                            requested_quantity=item.quantity,
                            current_stock=current_stock,
                        ),
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
                    part_code=(
                        self._inventory_cell_text(
                            df,
                            frame_index,
                            self.inventory_part_code_header(),
                        )
                        or item.part_code
                    ),
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

    # 출고 요청 수량과 현재 재고의 의미가 명확히 드러나는 부족 메시지를 생성합니다.
    def _build_outbound_quantity_exceeds_stock_message(
        self,
        part: str,
        requested_quantity: int,
        current_stock: int,
    ) -> str:
        return (
            f'{part} 출고 수량이 현재 재고보다 큽니다: '
            f'요청 수량: {requested_quantity}개, 현재 재고: {current_stock}개'
        )

    def _inventory_cell_text(
        self,
        frame: pd.DataFrame,
        row_index: int,
        column_name: str | None,
    ) -> str:
        if column_name is None or column_name not in frame.columns:
            return ''
        return str(frame.at[row_index, column_name]).strip()

    def _parse_stock(self, value: object) -> int | None:
        try:
            number = float(str(value).strip())
        except ValueError:
            return None
        if not number.is_integer():
            return None
        return int(number)

    # 주문 워크시트 행의 지정된 열 값을 안전하게 문자열로 읽습니다.
    def _row_cell_text(self, row: list[object], col_index: int) -> str:
        if col_index < 0 or col_index >= len(row):
            return ''
        return str(row[col_index]).strip()

    # 주문 워크시트 기록 행을 방향과 상태값에 맞춰 생성합니다.
    def _order_row(
        self,
        direction: str,
        request_text: str,
        agent_name: str,
        change: StockChange,
        status: str = ORDER_STATUS_SUCCESS,
        order_id: str | None = None,
    ) -> list[object]:
        amount: int | str = (
            change.unit_price * change.quantity
            if change.unit_price is not None
            else ''
        )
        header_values: dict[str, object] = {
            ORDER_HEADER_RECORDED_AT: datetime.now(timezone.utc).isoformat(),
            ORDER_HEADER_ORDER_ID: order_id or '',
            ORDER_HEADER_AGENT_NAME: agent_name,
            ORDER_HEADER_DIRECTION: (
                ORDER_DIRECTION_INBOUND
                if direction == 'inbound'
                else ORDER_DIRECTION_OUTBOUND
            ),
            ORDER_HEADER_PART_CODE: change.part_code or '',
            ORDER_HEADER_QUANTITY: change.quantity,
            ORDER_HEADER_BEFORE_STOCK: change.before_stock,
            ORDER_HEADER_AFTER_STOCK: change.after_stock,
            ORDER_HEADER_PRICE: amount,
            ORDER_HEADER_REQUEST_TEXT: request_text,
            ORDER_HEADER_STATUS: status,
        }
        return [
            header_values.get(header, '')
            for header in self.config.order_headers
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
            '부품',
            '품목',
            '상품',
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
