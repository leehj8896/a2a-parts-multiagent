from __future__ import annotations

import importlib
import unittest

from pathlib import Path


PREFIX_MODULES = (
    'local_inventory_query',
    'peer_inventory_query',
    'stock_inbound',
    'stock_outbound',
    'peer_stock_inbound',
    'peer_stock_outbound',
)


class RequestModuleStructureTest(unittest.TestCase):
    def test_prefix_modules_live_under_parts_multiagent_root(self) -> None:
        root = Path(__file__).resolve().parents[1] / 'parts_multiagent'

        for module_name in PREFIX_MODULES:
            with self.subTest(module_name=module_name):
                module_dir = root / module_name
                self.assertTrue(module_dir.is_dir())
                for file_name in (
                    '__init__.py',
                    'request.py',
                    'response.py',
                    'parser.py',
                    'handler.py',
                ):
                    self.assertTrue((module_dir / file_name).is_file())

    def test_prefix_modules_export_parse_and_handle(self) -> None:
        for module_name in PREFIX_MODULES:
            with self.subTest(module_name=module_name):
                module = importlib.import_module(
                    f'parts_multiagent.{module_name}'
                )
                self.assertTrue(callable(module.parse))
                self.assertTrue(callable(module.handle))


if __name__ == '__main__':
    unittest.main()
