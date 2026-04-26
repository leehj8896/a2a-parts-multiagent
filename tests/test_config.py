from __future__ import annotations

import os
import tempfile
import unittest

from unittest.mock import patch

from parts_multiagent.config import (
    DEFAULT_ORDER_HEADERS,
    load_agent_dotenv,
    load_config,
)


REQUIRED_ENV = {
    'AGENT_NAME': 'A',
    'GOOGLE_SERVICE_ACCOUNT_FILE': '/tmp/service-account.json',
    'GOOGLE_SHEET_ID': 'sheet-123',
}


class ConfigTest(unittest.TestCase):
    def test_loads_order_headers_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                **REQUIRED_ENV,
                'GOOGLE_SHEET_ORDER_HEADERS': (
                    '기록시각,주문번호,에이전트,구분,부품번호,수량,변경전재고,'
                    '변경후재고,가격,요청내용,상태'
                ),
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(
            config.google_sheet.order_headers,
            DEFAULT_ORDER_HEADERS,
        )

    def test_missing_order_headers_uses_default(self) -> None:
        with patch.dict(os.environ, REQUIRED_ENV, clear=True):
            config = load_config()

        self.assertEqual(
            config.google_sheet.order_headers,
            DEFAULT_ORDER_HEADERS,
        )

    def test_loads_supplier_delivery_time_mapping_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                **REQUIRED_ENV,
                'SUPPLIER_DELIVERY_TIME_BY_AGENT': 'B=4,C=24',
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(
            config.supplier_delivery_time_by_agent,
            {'B': 4, 'C': 24},
        )

    def test_missing_supplier_delivery_time_mapping_defaults_to_empty(self) -> None:
        with patch.dict(os.environ, REQUIRED_ENV, clear=True):
            config = load_config()

        self.assertEqual(config.supplier_delivery_time_by_agent, {})

    def test_invalid_supplier_delivery_time_entries_raise_error(self) -> None:
        with patch.dict(
            os.environ,
            {
                **REQUIRED_ENV,
                'SUPPLIER_DELIVERY_TIME_BY_AGENT': (
                    'B=4,invalid,C=1일'
                ),
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                load_config()

    def test_non_positive_supplier_delivery_time_entries_raise_error(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                **REQUIRED_ENV,
                'SUPPLIER_DELIVERY_TIME_BY_AGENT': 'B=0,C=-1',
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                load_config()

    def test_load_agent_dotenv_reads_agent_specific_delivery_time(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            agent_env_path = os.path.join(temp_dir, '.env.a')
            with open(agent_env_path, 'w', encoding='utf-8') as agent_env_file:
                agent_env_file.write(
                    'SUPPLIER_DELIVERY_TIME_BY_AGENT="B=4,C=24"\n'
                )

            try:
                os.chdir(temp_dir)
                with patch.dict(
                    os.environ,
                    {**REQUIRED_ENV, 'AGENT_NAME': 'A'},
                    clear=True,
                ):
                    load_agent_dotenv()
                    config = load_config()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(
            config.supplier_delivery_time_by_agent,
            {'B': 4, 'C': 24},
        )

    def test_loads_supported_agent_log_colors(self) -> None:
        with patch.dict(
            os.environ,
            {**REQUIRED_ENV, 'LOG_COLORS': 'A=cyan,B=yellow'},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.agent_log_colors, {'A': 'cyan', 'B': 'yellow'})

    def test_missing_log_colors_defaults_to_empty_mapping(self) -> None:
        with patch.dict(os.environ, REQUIRED_ENV, clear=True):
            config = load_config()

        self.assertEqual(config.agent_log_colors, {})

    def test_unsupported_log_colors_are_ignored(self) -> None:
        with patch.dict(
            os.environ,
            {**REQUIRED_ENV, 'LOG_COLORS': 'A=chartreuse,B=magenta'},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.agent_log_colors, {'B': 'magenta'})


if __name__ == '__main__':
    unittest.main()
