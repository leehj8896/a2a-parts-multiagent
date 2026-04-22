from __future__ import annotations

import unittest

from parts_multiagent.google_sheet_inventory import (
    GoogleSheetConfig,
    GoogleSheetInventory,
)


def inventory(values):
    return GoogleSheetInventory(
        GoogleSheetConfig(
            service_account_file='/tmp/service-account.json',
            spreadsheet_id='sheet-123',
            worksheet='inventory',
        ),
        values_loader=lambda: values,
    )


class GoogleSheetInventoryTest(unittest.TestCase):
    def test_queries_specific_part(self) -> None:
        _, result = inventory(
            [
                ['part_number', 'part_name', 'stock', 'location'],
                ['BRK-001', 'Brake Pad', '28', 'A-01'],
                ['FLT-101', 'Oil Filter', '7', 'A-02'],
            ]
        ).query('FLT-101 재고 알려줘')

        self.assertIn('FLT-101', result)
        self.assertIn('Oil Filter', result)
        self.assertNotIn('BRK-001', result)

    def test_queries_low_stock_with_default_threshold(self) -> None:
        _, result = inventory(
            [
                ['part_number', 'part_name', 'stock', 'location'],
                ['BRK-001', 'Brake Pad', '28', 'A-01'],
                ['FLT-101', 'Oil Filter', '7', 'A-02'],
                ['BLT-404', 'Timing Belt', '3', 'A-03'],
            ]
        ).query('재고 부족 품목 알려줘')

        self.assertIn('FLT-101', result)
        self.assertIn('BLT-404', result)
        self.assertNotIn('BRK-001', result)

    def test_queries_total_stock(self) -> None:
        _, result = inventory(
            [
                ['part_number', 'part_name', 'stock', 'location'],
                ['BRK-001', 'Brake Pad', '28', 'A-01'],
                ['FLT-101', 'Oil Filter', '7', 'A-02'],
            ]
        ).query('전체 재고 합계')

        self.assertIn('stock 합계: 35', result)

    def test_empty_sheet_has_clear_message(self) -> None:
        context, result = inventory([]).query('재고 알려줘')

        self.assertIn('No rows found', context)
        self.assertIn('조회할 재고 행을 찾지 못했습니다', result)

    def test_loader_failure_has_clear_message(self) -> None:
        sheet = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file='/tmp/service-account.json',
                spreadsheet_id='sheet-123',
                worksheet='missing',
            ),
            values_loader=lambda: (_ for _ in ()).throw(
                RuntimeError('worksheet not found')
            ),
        )

        context, result = sheet.query('재고 알려줘')

        self.assertIn('sheet-123/missing', context)
        self.assertIn('Google Sheet 조회에 실패했습니다', result)
        self.assertIn('worksheet not found', result)


if __name__ == '__main__':
    unittest.main()
