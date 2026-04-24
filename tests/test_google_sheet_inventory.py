from __future__ import annotations

import unittest

from parts_multiagent.google_sheet_inventory import (
    GoogleSheetConfig,
    GoogleSheetInventory,
    StockCellUpdate,
    StockChangeItem,
)
from parts_multiagent.stock_inbound import parse as parse_stock_inbound


INVENTORY_HEADERS = ['부품번호', '부품명', '수량', '가격(원)']


def inventory(values):
    return GoogleSheetInventory(
        GoogleSheetConfig(
            service_account_file='/tmp/service-account.json',
            spreadsheet_id='sheet-123',
            inventory_worksheet='inventory',
            order_worksheet='orders',
            inventory_headers=tuple(INVENTORY_HEADERS),
        ),
        values_loader=lambda: values,
    )


class GoogleSheetInventoryTest(unittest.TestCase):
    def test_queries_specific_part(self) -> None:
        _, result = inventory(
            [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '28', '12000'],
                ['FLT-101', 'Oil Filter', '7', '5000'],
            ]
        ).query('FLT-101 재고 알려줘')

        self.assertIn('FLT-101', result)
        self.assertIn('Oil Filter', result)
        self.assertNotIn('BRK-001', result)

    def test_queries_low_stock_with_default_threshold(self) -> None:
        _, result = inventory(
            [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '28', '12000'],
                ['FLT-101', 'Oil Filter', '7', '5000'],
                ['BLT-404', 'Timing Belt', '3', '21000'],
            ]
        ).query('재고 부족 품목 알려줘')

        self.assertIn('FLT-101', result)
        self.assertIn('BLT-404', result)
        self.assertNotIn('BRK-001', result)

    def test_queries_total_stock(self) -> None:
        _, result = inventory(
            [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '28', '12000'],
                ['FLT-101', 'Oil Filter', '7', '5000'],
            ]
        ).query('전체 재고 합계')

        self.assertIn('수량 합계: 35', result)

    def test_empty_sheet_has_clear_message(self) -> None:
        context, result = inventory([]).query('재고 알려줘')

        self.assertIn('행을 찾지 못했습니다', context)
        self.assertIn('조회할 재고 행을 찾지 못했습니다', result)

    def test_loader_failure_has_clear_message(self) -> None:
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='missing',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: (_ for _ in ()).throw(
                RuntimeError('worksheet not found')
            ),
        )

        context, result = sheet.query('재고 알려줘')

        self.assertIn('missing', context)
        self.assertIn('Google Sheet를 조회하지 못했습니다', result)
        self.assertIn('worksheet not found', result)

    def test_inbound_updates_stock_and_appends_order_rows(self) -> None:
        stock_updates = []
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '28', '12000'],
                ['FLT-101', 'Oil Filter', '7', '5000'],
            ],
            stock_writer=stock_updates.extend,
            order_appender=order_rows.extend,
        )

        _, result = sheet.change_stock(
            'inbound',
            [StockChangeItem('FLT-101', 3), StockChangeItem('BRK-001', 2)],
            '/local-stock-inbound FLT-101 3, BRK-001 2',
            'A',
        )

        self.assertIn('입고 처리 완료: 2건', result)
        self.assertEqual(
            stock_updates,
            [StockCellUpdate(3, 3, 10), StockCellUpdate(2, 3, 30)],
        )
        self.assertEqual(len(order_rows), 2)
        self.assertEqual(order_rows[0][1:10], ['A', '입고', 'FLT-101', 3, 7, 10, 15000, '/local-stock-inbound FLT-101 3, BRK-001 2', '성공'])

    def test_outbound_rejects_when_stock_is_not_enough(self) -> None:
        stock_updates = []
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', '5000'],
            ],
            stock_writer=stock_updates.extend,
            order_appender=order_rows.extend,
        )

        _, result = sheet.change_stock(
            'outbound',
            [StockChangeItem('FLT-101', 8)],
            '/local-stock-outbound FLT-101 8',
            'A',
        )

        self.assertIn('출고 수량이 현재 재고보다 큽니다', result)
        self.assertEqual(stock_updates, [])
        self.assertEqual(order_rows, [])

    def test_inbound_adds_new_row_when_part_not_found(self) -> None:
        stock_updates = []
        order_rows = []
        inventory_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '28', '12000'],
            ],
            stock_writer=stock_updates.extend,
            order_appender=order_rows.extend,
            inventory_appender=inventory_rows.extend,
        )

        _, result = sheet.change_stock(
            'inbound',
            [StockChangeItem('FLT-001', 5)],
            '/local-stock-inbound FLT-001 5',
            'A',
        )

        self.assertIn('입고 처리 완료: 1건', result)
        self.assertIn('(신규)', result)
        self.assertIn('0 -> 5', result)
        self.assertEqual(stock_updates, [])
        self.assertEqual(len(inventory_rows), 1)
        row = inventory_rows[0]
        self.assertIn('FLT-001', row)
        self.assertIn(5, row)
        self.assertEqual(len(order_rows), 1)
        self.assertEqual(order_rows[0][1:10], ['A', '입고', 'FLT-001', 5, 0, 5, '', '/local-stock-inbound FLT-001 5', '성공'])

    def test_inbound_mixes_existing_and_new_parts(self) -> None:
        stock_updates = []
        order_rows = []
        inventory_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '10', '12000'],
            ],
            stock_writer=stock_updates.extend,
            order_appender=order_rows.extend,
            inventory_appender=inventory_rows.extend,
        )

        _, result = sheet.change_stock(
            'inbound',
            [StockChangeItem('BRK-001', 2), StockChangeItem('FLT-001', 3)],
            '/local-stock-inbound BRK-001 2, FLT-001 3',
            'A',
        )

        self.assertIn('입고 처리 완료: 2건', result)
        self.assertEqual(stock_updates, [StockCellUpdate(2, 3, 12)])
        self.assertEqual(len(inventory_rows), 1)
        self.assertEqual(len(order_rows), 2)

    def test_outbound_returns_error_when_part_not_found(self) -> None:
        stock_updates = []
        inventory_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '10', '12000'],
            ],
            stock_writer=stock_updates.extend,
            order_appender=lambda rows: None,
            inventory_appender=inventory_rows.extend,
        )

        _, result = sheet.change_stock(
            'outbound',
            [StockChangeItem('FLT-001', 1)],
            '/local-stock-outbound FLT-001 1',
            'A',
        )

        self.assertIn('맞는 품목을 찾지 못했습니다', result)
        self.assertEqual(stock_updates, [])
        self.assertEqual(inventory_rows, [])

    def test_inbound_includes_price_total_when_price_column_exists(self) -> None:
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', '5000'],
                ['BRK-001', 'Brake Pad', '10', '12000'],
            ],
            stock_writer=lambda updates: None,
            order_appender=order_rows.extend,
        )

        _, result = sheet.change_stock(
            'inbound',
            [StockChangeItem('FLT-101', 3), StockChangeItem('BRK-001', 1)],
            '/local-stock-inbound FLT-101 3, BRK-001 1',
            'A',
        )

        self.assertIn('단가: 5,000원, 소계: 15,000원', result)
        self.assertIn('단가: 12,000원, 소계: 12,000원', result)
        self.assertIn('합계 금액: 27,000원', result)
        self.assertEqual(order_rows[0][7], 15000)
        self.assertEqual(order_rows[1][7], 12000)

    def test_inbound_overwrites_existing_price_when_unit_price_given(
        self,
    ) -> None:
        stock_updates = []
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', '4500'],
            ],
            stock_writer=stock_updates.extend,
            order_appender=order_rows.extend,
        )

        _, result = sheet.change_stock(
            'inbound',
            [StockChangeItem('FLT-101', 3, unit_price=5000)],
            '/local-stock-inbound FLT-101 3',
            'A',
        )

        self.assertIn('단가: 5,000원, 소계: 15,000원', result)
        self.assertEqual(
            stock_updates,
            [StockCellUpdate(2, 3, 10), StockCellUpdate(2, 4, 5000)],
        )
        self.assertEqual(order_rows[0][7], 15000)

    def test_inbound_new_row_includes_unit_price_when_given(self) -> None:
        inventory_rows = []
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['BRK-001', 'Brake Pad', '28', '12000'],
            ],
            stock_writer=lambda updates: None,
            order_appender=order_rows.extend,
            inventory_appender=inventory_rows.extend,
        )

        _, result = sheet.change_stock(
            'inbound',
            [StockChangeItem('FLT-001', 5, unit_price=8000)],
            '/local-stock-inbound FLT-001 5',
            'A',
        )

        self.assertIn('단가: 8,000원, 소계: 40,000원', result)
        self.assertEqual(len(inventory_rows), 1)
        self.assertEqual(inventory_rows[0], ['', 'FLT-001', 5, 8000])
        self.assertEqual(order_rows[0][7], 40000)

    def test_inbound_prefers_item_unit_price_over_sheet_price(self) -> None:
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', '4500'],
            ],
            stock_writer=lambda updates: None,
            order_appender=order_rows.extend,
        )

        _, result = sheet.change_stock(
            'inbound',
            [StockChangeItem('FLT-101', 2, unit_price=5000)],
            '/local-stock-inbound FLT-101 2',
            'A',
        )

        self.assertIn('단가: 5,000원, 소계: 10,000원', result)
        self.assertNotIn('단가: 4,500원', result)
        self.assertEqual(order_rows[0][7], 10000)

    def test_outbound_includes_price_total_when_price_column_exists(self) -> None:
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', '5000'],
                ['BRK-001', 'Brake Pad', '10', '12000'],
            ],
            stock_writer=lambda updates: None,
            order_appender=order_rows.extend,
        )

        _, result = sheet.change_stock(
            'outbound',
            [StockChangeItem('FLT-101', 3), StockChangeItem('BRK-001', 1)],
            '/local-stock-outbound FLT-101 3, BRK-001 1',
            'A',
        )

        self.assertIn('출고 처리 완료: 2건', result)
        self.assertIn('단가: 5,000원, 소계: 15,000원', result)
        self.assertIn('단가: 12,000원, 소계: 12,000원', result)
        self.assertIn('합계 금액: 27,000원', result)
        self.assertEqual(order_rows[0][7], 15000)
        self.assertEqual(order_rows[1][7], 12000)

    def test_outbound_omits_price_total_when_price_missing(self) -> None:
        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', ''],
            ],
            stock_writer=lambda updates: None,
            order_appender=order_rows.extend,
        )

        _, result = sheet.change_stock(
            'outbound',
            [StockChangeItem('FLT-101', 1)],
            '/local-stock-outbound FLT-101 1',
            'A',
        )

        self.assertIn('출고 처리 완료: 1건', result)
        self.assertNotIn('단가:', result)
        self.assertNotIn('소계:', result)
        self.assertNotIn('합계 금액:', result)
        self.assertEqual(order_rows[0][7], '')

    def test_rejects_location_header(self) -> None:
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                ['부품번호', '부품명', '수량', 'location'],
                ['FLT-101', 'Oil Filter', '7', 'A-01'],
            ],
            stock_writer=lambda updates: None,
            order_appender=lambda rows: None,
        )

        _, result = sheet.query('재고 알려줘')

        self.assertIn('위치(location/위치) 열은 지원하지 않습니다', result)
        self.assertIn("기대 헤더: ['부품번호', '부품명', '수량', '가격(원)']", result)
        self.assertIn("현재 헤더: ['부품번호', '부품명', '수량', 'location']", result)

    def test_rejects_korean_location_header(self) -> None:
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                ['부품번호', '부품명', '수량', '위치'],
                ['FLT-101', 'Oil Filter', '7', '창고C'],
            ],
            stock_writer=lambda updates: None,
            order_appender=lambda rows: None,
        )

        _, result = sheet.query('재고 알려줘')

        self.assertIn('위치(location/위치) 열은 지원하지 않습니다', result)
        self.assertIn("현재 헤더: ['부품번호', '부품명', '수량', '위치']", result)

    def test_rejects_five_column_inventory_sheet(self) -> None:
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                [*INVENTORY_HEADERS, 'memo'],
                ['FLT-101', 'Oil Filter', '7', '5000', '핫셀러'],
            ],
            stock_writer=lambda updates: None,
            order_appender=lambda rows: None,
        )

        _, result = sheet.query('재고 알려줘')

        self.assertIn('헤더 열 개수가 올바르지 않습니다', result)
        self.assertIn("기대 헤더: ['부품번호', '부품명', '수량', '가격(원)']", result)
        self.assertIn("현재 헤더: ['부품번호', '부품명', '수량', '가격(원)', 'memo']", result)

    def test_order_row_length_matches_order_headers(self) -> None:
        from parts_multiagent.google_sheet_inventory import ORDER_HEADERS

        order_rows = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', '5000'],
            ],
            stock_writer=lambda updates: None,
            order_appender=order_rows.extend,
        )

        sheet.change_stock(
            'outbound',
            [StockChangeItem('FLT-101', 1)],
            '/local-stock-outbound FLT-101 1',
            'A',
        )

        self.assertEqual(len(order_rows[0]), len(ORDER_HEADERS))

    def test_update_rejects_multiple_matches_without_writing(self) -> None:
        stock_updates = []
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                inventory_worksheet='inventory',
                order_worksheet='orders',
                inventory_headers=tuple(INVENTORY_HEADERS),
            ),
            values_loader=lambda: [
                INVENTORY_HEADERS,
                ['FLT-101', 'Oil Filter', '7', '5000'],
                ['FLT-101-A', 'Oil Filter Alt', '5', '5200'],
            ],
            stock_writer=stock_updates.extend,
            order_appender=lambda rows: None,
        )

        _, result = sheet.change_stock(
            'outbound',
            [StockChangeItem('FLT-101', 1)],
            '/local-stock-outbound FLT-101 1',
            'A',
        )

        self.assertIn('여러 행이 매칭', result)
        self.assertEqual(stock_updates, [])


class StockInboundParserTest(unittest.TestCase):
    def test_structured_payload_stays_structured(self) -> None:
        request = parse_stock_inbound('B FLT-101 3, BRK-001 2')

        self.assertEqual(request.agent_name, 'B')
        self.assertEqual(request.raw_items, 'FLT-101 3, BRK-001 2')
        self.assertEqual([item.part for item in request.items], ['FLT-101', 'BRK-001'])


if __name__ == '__main__':
    unittest.main()
