from __future__ import annotations

import logging
import unittest

from parts_multiagent.logging_config import AgentPrefixFormatter


class LoggingConfigTest(unittest.TestCase):
    def test_formatter_adds_plain_agent_prefix_without_color(self) -> None:
        formatter = AgentPrefixFormatter('A', {})
        record = logging.LogRecord(
            name='parts_multiagent.test',
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg='hello',
            args=(),
            exc_info=None,
        )

        self.assertEqual(
            formatter.format(record),
            'INFO:parts_multiagent.test:[A] hello',
        )

    def test_formatter_colors_agent_prefix(self) -> None:
        formatter = AgentPrefixFormatter('A', {'B': 'cyan'})
        record = logging.LogRecord(
            name='parts_multiagent.test',
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg='hello',
            args=(),
            exc_info=None,
        )
        record.agent_name = 'B'

        formatted = formatter.format(record)

        self.assertEqual(
            formatted,
            '\033[36mINFO:parts_multiagent.test:[B] hello\033[0m',
        )
        self.assertTrue(formatted.endswith(' hello\033[0m'))

    def test_formatter_uses_default_agent_when_record_has_no_agent(self) -> None:
        formatter = AgentPrefixFormatter('A', {'A': 'yellow'})
        record = logging.LogRecord(
            name='parts_multiagent.test',
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg='hello',
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        self.assertEqual(
            formatted,
            '\033[33mINFO:parts_multiagent.test:[A] hello\033[0m',
        )


if __name__ == '__main__':
    unittest.main()
