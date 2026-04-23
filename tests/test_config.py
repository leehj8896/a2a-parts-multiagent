from __future__ import annotations

import os
import unittest

from unittest.mock import patch

from parts_multiagent.config import load_config


REQUIRED_ENV = {
    'AGENT_NAME': 'A',
    'GOOGLE_SERVICE_ACCOUNT_FILE': '/tmp/service-account.json',
    'GOOGLE_SHEET_ID': 'sheet-123',
}


class ConfigTest(unittest.TestCase):
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
