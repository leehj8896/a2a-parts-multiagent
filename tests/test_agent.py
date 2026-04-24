from __future__ import annotations

import unittest

from parts_multiagent.agent import EMPTY_QUERY_MESSAGE, PartsMultiAgent
from parts_multiagent.config import GoogleSheetSettings, PartsAgentConfig
from parts_multiagent.constants.prefixes import (
    LOCAL_AGENT_PREFIX,
    PEER_AGENTS_PREFIX,
    USER_QUERY_PREFIXES,
)


def agent_config() -> PartsAgentConfig:
    return PartsAgentConfig(
        agent_name='A',
        agent_description='warehouse A',
        app_url='http://localhost:10001',
        google_sheet=GoogleSheetSettings(
            service_account_file='/tmp/service-account.json',
            spreadsheet_id='sheet-a',
            inventory_worksheet='inventory',
            order_worksheet='orders',
            inventory_headers=('부품번호', '부품명', '수량', '가격(원)'),
        ),
        llm_base_url='http://localhost:11434/v1',
        llm_model='test-model',
        peer_agent_urls=[],
        host='0.0.0.0',
        port=10001,
        agent_log_colors={},
    )


class FakeInventory:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, question: str) -> tuple[str, str]:
        self.queries.append(question)
        return 'context', f'raw:{question}'

    def describe(self) -> str:
        return 'fake inventory'


class FakeLlm:
    def __init__(self) -> None:
        self.summaries: list[tuple[str, str, str]] = []

    async def summarize_answer(
        self,
        query: str,
        csv_context: str,
        raw_result: str,
    ) -> str:
        self.summaries.append((query, csv_context, raw_result))
        return f'summary:{query}:{raw_result}'


class FakePeers:
    def __init__(
        self,
        names: list[str] | None = None,
        errors: list[str] | None = None,
        failing_names: set[str] | None = None,
    ) -> None:
        self.names = names or []
        self.errors = errors or []
        self.failing_names = failing_names or set()
        self.refresh_count = 0
        self.sent: list[tuple[str, str]] = []

    async def refresh(self) -> list[str]:
        self.refresh_count += 1
        return self.errors

    def agent_names(self) -> list[str]:
        return self.names

    async def send_message(self, agent_name: str, text: str) -> str:
        self.sent.append((agent_name, text))
        if agent_name in self.failing_names:
            raise RuntimeError(f'{agent_name} is down')
        return f'peer:{agent_name}:{text}'


def fake_agent(peers: FakePeers | None = None) -> PartsMultiAgent:
    agent = PartsMultiAgent(agent_config())
    agent.inventory = FakeInventory()
    agent.llm = FakeLlm()
    agent.peers = peers or FakePeers()
    return agent


class PrefixConstantsTest(unittest.TestCase):
    def test_user_query_prefixes_list_supported_prefixes(self) -> None:
        self.assertEqual(
            USER_QUERY_PREFIXES,
            (LOCAL_AGENT_PREFIX, PEER_AGENTS_PREFIX),
        )


class PartsMultiAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_prefix_queries_only_local_inventory(self) -> None:
        peers = FakePeers(names=['B'])
        agent = fake_agent(peers)

        result = await agent.invoke('/local FLT-101 재고')

        self.assertIn('summary:FLT-101 재고:raw:FLT-101 재고', result)
        self.assertEqual(agent.inventory.queries, ['FLT-101 재고'])
        self.assertEqual(peers.refresh_count, 0)
        self.assertEqual(peers.sent, [])

    async def test_peer_prefix_queries_only_peers_with_local_prefix(
        self,
    ) -> None:
        peers = FakePeers(names=['B', 'C'])
        agent = fake_agent(peers)

        result = await agent.invoke('/peers FLT-101 재고')

        self.assertIn('## 다른 agent 조회', result)
        self.assertIn('[B] 응답입니다.', result)
        self.assertIn('[C] 응답입니다.', result)
        self.assertEqual(agent.inventory.queries, [])
        self.assertEqual(
            peers.sent,
            [
                ('B', '/local FLT-101 재고'),
                ('C', '/local FLT-101 재고'),
            ],
        )

    async def test_plain_query_returns_local_and_peer_sections(self) -> None:
        peers = FakePeers(names=['B'])
        agent = fake_agent(peers)

        result = await agent.invoke('FLT-101 재고')

        local_index = result.index('## 내 agent 조회')
        peer_index = result.index('## 다른 agent 조회')
        self.assertLess(local_index, peer_index)
        self.assertIn('[A] 응답입니다.', result)
        self.assertIn('[B] 응답입니다.', result)
        self.assertEqual(agent.inventory.queries, ['FLT-101 재고'])
        self.assertEqual(peers.sent, [('B', '/local FLT-101 재고')])

    async def test_similar_prefix_is_not_treated_as_command(self) -> None:
        agent = fake_agent()

        result = await agent.invoke('/locality FLT-101 재고')

        self.assertIn('## 내 agent 조회', result)
        self.assertEqual(agent.inventory.queries, ['/locality FLT-101 재고'])

    async def test_prefix_without_task_returns_clear_message(self) -> None:
        for query in ('/local', '/peers'):
            with self.subTest(query=query):
                peers = FakePeers(names=['B'])
                agent = fake_agent(peers)

                result = await agent.invoke(query)

                self.assertEqual(result, EMPTY_QUERY_MESSAGE)
                self.assertEqual(agent.inventory.queries, [])
                self.assertEqual(peers.refresh_count, 0)
                self.assertEqual(peers.sent, [])

    async def test_peer_query_without_peers_has_clear_message(self) -> None:
        peers = FakePeers(errors=['http://localhost:10002: timeout'])
        agent = fake_agent(peers)

        result = await agent.invoke('/peers FLT-101 재고')

        self.assertIn('조회 가능한 다른 agent가 없습니다.', result)
        self.assertIn('AgentCard를 가져오지 못했습니다.', result)
        self.assertIn('http://localhost:10002: timeout', result)

    async def test_peer_failure_is_included_in_response(self) -> None:
        peers = FakePeers(names=['B'], failing_names={'B'})
        agent = fake_agent(peers)

        result = await agent.invoke('/peers FLT-101 재고')

        self.assertIn('[B] 요청 실패: RuntimeError: B is down', result)


if __name__ == '__main__':
    unittest.main()
