from __future__ import annotations

import logging
import unittest

from io import StringIO

from parts_multiagent.constants.skill_prefixes import SKILL_INVENTORY_LOOKUP_LOCAL
from parts_multiagent.domain.inventory.utils.inventory_log import (
    log_peer_agent_response,
    log_structured_skill_success,
)
from parts_multiagent.domain.inventory_lookup_local.types.request import (
    LocalInventoryQueryRequest,
)
from parts_multiagent.domain.inventory_lookup_local.types.response import (
    LocalInventoryQueryResponse,
)
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

    def test_formatter_colors_c_agent_prefix(self) -> None:
        formatter = AgentPrefixFormatter('A', {'C': 'magenta'})
        record = logging.LogRecord(
            name='parts_multiagent.test',
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg='hello',
            args=(),
            exc_info=None,
        )
        record.agent_name = 'C'

        formatted = formatter.format(record)

        self.assertEqual(
            formatted,
            '\033[35mINFO:parts_multiagent.test:[C] hello\033[0m',
        )

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

    def test_structured_inventory_log_keeps_table_rendering(self) -> None:
        logger = logging.getLogger('parts_multiagent.test.inventory_log')
        request = LocalInventoryQueryRequest(query='FLT-101 재고')
        response = LocalInventoryQueryResponse(
            status='success',
            message='부품번호,부품명,수량\nFLT-101,Oil Filter,7',
        )

        with self.assertLogs(logger.name, level='INFO') as logs:
            log_structured_skill_success(
                logger=logger,
                agent_name='B',
                skill_id=SKILL_INVENTORY_LOOKUP_LOCAL,
                request=request,
                response=response,
            )

        logged = '\n'.join(logs.output)
        self.assertIn('skill 실행 완료: agent=B', logged)
        self.assertIn('응답_형식=표', logged)
        self.assertIn('| 부품번호', logged)
        self.assertIn('| FLT-101', logged)

    def test_peer_and_local_logs_use_each_agent_color(self) -> None:
        logger = logging.getLogger('parts_multiagent.test.mixed_colors')
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(
            AgentPrefixFormatter(
                'A',
                {'A': 'yellow', 'B': 'cyan'},
            )
        )
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        log_peer_agent_response(
            logger=logger,
            local_agent='A',
            source_agent='B',
            request_text='주문하기 B FLT-101 3개',
            response='B 응답',
        )
        log_peer_agent_response(
            logger=logger,
            local_agent='A',
            source_agent='A',
            request_text='주문하기 B FLT-101 3개',
            response='A 반영',
        )

        logged = stream.getvalue()

        self.assertIn('\033[36mINFO:parts_multiagent.test.mixed_colors:[B]', logged)
        self.assertIn('\033[33mINFO:parts_multiagent.test.mixed_colors:[A]', logged)
        self.assertIn('응답_에이전트=B', logged)
        self.assertIn('응답_에이전트=A', logged)


if __name__ == '__main__':
    unittest.main()
