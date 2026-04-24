from __future__ import annotations

import unittest

from parts_multiagent.agent import PartsMultiAgent
from parts_multiagent.config import GoogleSheetSettings, PartsAgentConfig
from parts_multiagent.constants.prefixes import (
    INVENTORY_LOOKUP_LOCAL_PREFIX,
    INVENTORY_LOOKUP_PEERS_PREFIX,
    LOCAL_STOCK_INBOUND_PREFIX,
    PEER_STOCK_OUTBOUND_PREFIX,
)
from parts_multiagent.constants.structured_payload_keys import (
    AGENT_NAME,
    ITEMS,
    PART,
    QUERY,
    QUANTITY,
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
        self.stock_changes: list[dict[str, object]] = []

    def query(self, question: str) -> tuple[str, str]:
        self.queries.append(question)
        return 'context', f'raw:{question}'

    def change_stock(
        self,
        *,
        direction: str,
        items: list[object],
        request_text: str,
        agent_name: str,
    ) -> tuple[None, str]:
        self.stock_changes.append(
            {
                'direction': direction,
                'items': items,
                'request_text': request_text,
                'agent_name': agent_name,
            }
        )
        return None, f'changed:{direction}:{request_text}:{agent_name}'

    def describe(self) -> str:
        return 'fake inventory'


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
        self.sent_text: list[tuple[str, str]] = []
        self.sent_structured: list[tuple[str, str, dict[str, object]]] = []

    async def refresh(self) -> list[str]:
        self.refresh_count += 1
        return self.errors

    def agent_names(self) -> list[str]:
        return self.names

    async def send_structured_message(
        self,
        agent_name: str,
        path: str,
        payload: dict[str, object],
        output_formats: list[str] | None = None,
    ) -> str:
        self.sent_structured.append((agent_name, path, payload))
        if agent_name in self.failing_names:
            raise RuntimeError(f'{agent_name} is down')
        return f'peer:{agent_name}:{path}'


def fake_agent(peers: FakePeers | None = None) -> PartsMultiAgent:
    agent = PartsMultiAgent(agent_config())
    agent.inventory = FakeInventory()
    agent.peers = peers or FakePeers()
    return agent


class PartsMultiAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_structured_local_inventory_queries_only_local_inventory(
        self,
    ) -> None:
        peers = FakePeers(names=['B'])
        agent = fake_agent(peers)

        result = await agent.invoke_structured(
            INVENTORY_LOOKUP_LOCAL_PREFIX,
            {QUERY: 'FLT-101 재고'},
        )

        self.assertIn('raw:FLT-101 재고', result)
        self.assertEqual(agent.inventory.queries, ['FLT-101 재고'])
        self.assertEqual(peers.refresh_count, 0)
        self.assertEqual(peers.sent_structured, [])

    async def test_structured_peer_inventory_queries_only_peers(
        self,
    ) -> None:
        peers = FakePeers(names=['B', 'C'])
        agent = fake_agent(peers)

        result = await agent.invoke_structured(
            INVENTORY_LOOKUP_PEERS_PREFIX,
            {QUERY: 'FLT-101 재고'},
        )

        self.assertIn('## 다른 agent 조회', result)
        self.assertIn('[B] 응답입니다.', result)
        self.assertIn('[C] 응답입니다.', result)
        self.assertEqual(agent.inventory.queries, [])
        self.assertEqual(
            peers.sent_structured,
            [
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                    {QUERY: 'FLT-101 재고'},
                ),
                (
                    'C',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                    {QUERY: 'FLT-101 재고'},
                ),
            ],
        )

    async def test_structured_unknown_path_returns_clear_message(self) -> None:
        agent = fake_agent()

        result = await agent.invoke_structured('/unknown', {QUERY: 'x'})

        self.assertIn('지원하지 않는 요청입니다', result)

    async def test_peer_query_without_peers_has_clear_message(self) -> None:
        peers = FakePeers(errors=['http://localhost:10002: timeout'])
        agent = fake_agent(peers)

        result = await agent.invoke_structured(
            INVENTORY_LOOKUP_PEERS_PREFIX,
            {QUERY: 'FLT-101 재고'},
        )

        self.assertIn('조회 가능한 다른 agent가 없습니다.', result)
        self.assertIn('AgentCard를 가져오지 못했습니다.', result)
        self.assertIn('http://localhost:10002: timeout', result)

    async def test_peer_failure_is_included_in_response(self) -> None:
        peers = FakePeers(names=['B'], failing_names={'B'})
        agent = fake_agent(peers)

        result = await agent.invoke_structured(
            INVENTORY_LOOKUP_PEERS_PREFIX,
            {QUERY: 'FLT-101 재고'},
        )

        self.assertIn('[B] 요청 실패: RuntimeError: B is down', result)

    async def test_structured_local_stock_inbound_is_routed_as_command(
        self,
    ) -> None:
        peers = FakePeers(names=['B', 'C'])
        agent = fake_agent(peers)

        result = await agent.invoke_structured(
            LOCAL_STOCK_INBOUND_PREFIX,
            {
                AGENT_NAME: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )

        self.assertIn('## peer 출고 결과 (B)', result)
        self.assertEqual(agent.inventory.queries, [])
        self.assertEqual(len(agent.inventory.stock_changes), 1)
        self.assertEqual(
            peers.sent_structured,
            [
                (
                    'B',
                    PEER_STOCK_OUTBOUND_PREFIX,
                    {
                        AGENT_NAME: 'A',
                        ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
                    },
                ),
            ],
        )


if __name__ == '__main__':
    unittest.main()
