from __future__ import annotations

import unittest
import json

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from a2a.types import AgentCapabilities, AgentCard, Message, Part, Role, SendMessageSuccessResponse, TextPart
from parts_multiagent.agent import PartsMultiAgent
from parts_multiagent.config import GoogleSheetSettings, PartsAgentConfig
from parts_multiagent.constants.prefixes import (
    INVENTORY_LOOKUP_LOCAL_PREFIX,
    INVENTORY_LOOKUP_PEERS_PREFIX,
    LOCAL_STOCK_INBOUND_PREFIX,
    ORDER_SELECTION_PREFIX,
    PAYMENT_COMPLETION_PREFIX,
    PEER_PAYMENT_COMPLETION_PREFIX,
    PEER_STOCK_OUTBOUND_PREFIX,
)
from parts_multiagent.constants.structured_payload_keys import (
    AGENT_NAME,
    ESTIMATED_DELIVERY_TIME,
    ITEMS,
    ORDER_ID,
    PAYMENT_URL,
    PART,
    QUERY,
    QUANTITY,
    RAW_ITEMS,
    SUPPLIER_AGENT,
    TOTAL_PRICE,
)
from parts_multiagent.domain.peer.peer_client import PeerDirectory
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    ITEMS_SHIPPED,
    MESSAGE,
    STATUS,
    UNIT_PRICE,
)
from parts_multiagent.utils.response_serialization import response_to_json_dict


def agent_config(
    agent_name: str = 'A',
    supplier_delivery_time_by_agent: dict[str, int] | None = None,
) -> PartsAgentConfig:
    return PartsAgentConfig(
        agent_name=agent_name,
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
        supplier_delivery_time_by_agent=supplier_delivery_time_by_agent or {},
    )


class FakeInventory:
    def __init__(
        self,
        change_stock_result: tuple[object, str] | None = None,
        pending_outbound_order_result: tuple[object, str, str] | None = None,
        local_pending_inbound_order_result: tuple[bool, str] | None = None,
        paid_inbound_order_result: tuple[bool, str, int, int, int] | None = None,
        paid_outbound_order_result: tuple[bool, str, int, int, int] | None = None,
    ) -> None:
        self.queries: list[str] = []
        self.stock_changes: list[dict[str, object]] = []
        self.pending_outbound_orders: list[dict[str, object]] = []
        self.local_pending_inbound_orders: list[dict[str, object]] = []
        self.paid_inbound_orders: list[dict[str, object]] = []
        self.paid_outbound_orders: list[dict[str, object]] = []
        self.change_stock_result = change_stock_result or (
            None,
            'changed:outbound:FLT-101 3:B',
        )
        self.pending_outbound_order_result = pending_outbound_order_result or (
            None,
            '[inventory] 주문 접수 완료: 1건\n- FLT-101: 3개 주문 접수 (현재 재고: 7개, 상태: 결제대기)',
            'a1b2c3d4e5',
        )
        self.local_pending_inbound_order_result = (
            local_pending_inbound_order_result
            or (True, '로컬 결제대기 주문 저장 완료: 1건')
        )
        self.paid_inbound_order_result = (
            paid_inbound_order_result
            or (
                True,
                '로컬 결제 확정 반영 완료(에이전트: A): 재고 업데이트 1건, 재고 신규행 0건, 주문상태 업데이트 1건',
                1,
                0,
                1,
            )
        )
        self.paid_outbound_order_result = (
            paid_outbound_order_result
            or (
                True,
                '로컬 결제 확정 반영 완료(에이전트: A): 재고 업데이트 1건, 재고 신규행 0건, 주문상태 업데이트 1건',
                1,
                0,
                1,
            )
        )

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
    ) -> tuple[object, str]:
        self.stock_changes.append(
            {
                'direction': direction,
                'items': items,
                'request_text': request_text,
                'agent_name': agent_name,
            }
        )
        return self.change_stock_result

    # 피어 주문 접수 요청을 테스트 더블에 기록하고 준비된 응답을 반환합니다.
    def register_pending_outbound_order(
        self,
        *,
        items: list[object],
        request_text: str,
        agent_name: str,
    ) -> tuple[object, str, str]:
        self.pending_outbound_orders.append(
            {
                'items': items,
                'request_text': request_text,
                'agent_name': agent_name,
            }
        )
        return self.pending_outbound_order_result

    # 주문선택 성공 후 로컬 결제대기 입고 행 저장 호출을 기록합니다.
    def register_local_pending_inbound_order(
        self,
        *,
        order_id: str,
        items: list[object],
        request_text: str,
        agent_name: str,
    ) -> tuple[bool, str]:
        self.local_pending_inbound_orders.append(
            {
                'order_id': order_id,
                'items': items,
                'request_text': request_text,
                'agent_name': agent_name,
            }
        )
        return self.local_pending_inbound_order_result

    # 결제완료 후 로컬 결제 확정 반영 호출을 기록합니다.
    def apply_paid_inbound_order(
        self,
        order_id: str,
        agent_name: str,
    ) -> tuple[bool, str, int, int, int]:
        self.paid_inbound_orders.append(
            {'order_id': order_id, 'agent_name': agent_name}
        )
        return self.paid_inbound_order_result

    # 피어결제완료 후 로컬 출고 결제 확정 반영 호출을 기록합니다.
    def apply_paid_outbound_order(
        self,
        order_id: str,
        agent_name: str,
    ) -> tuple[bool, str, int, int, int]:
        self.paid_outbound_orders.append(
            {'order_id': order_id, 'agent_name': agent_name}
        )
        return self.paid_outbound_order_result

    def describe(self) -> str:
        return 'fake inventory'


class FakePeers:
    def __init__(
        self,
        names: list[str] | None = None,
        errors: list[str] | None = None,
        failing_names: set[str] | None = None,
        responses: dict[tuple[str, str], str] | None = None,
        names_after_refresh: list[str] | None = None,
        strict_registered_names: bool = False,
    ) -> None:
        self.names = names or []
        self.errors = errors or []
        self.failing_names = failing_names or set()
        self.responses = responses or {}
        self.names_after_refresh = names_after_refresh
        self.strict_registered_names = strict_registered_names
        self.refresh_count = 0
        self.sent_text: list[tuple[str, str]] = []
        self.sent_structured: list[tuple[str, str, dict[str, object]]] = []

    async def refresh(self) -> list[str]:
        self.refresh_count += 1
        if self.names_after_refresh is not None:
            self.names = self.names_after_refresh
        return self.errors

    def agent_names(self) -> list[str]:
        return self.names

    async def send_structured_message(
        self,
        agent_name: str,
        path: str,
        payload: dict[str, object],
        output_formats: list[str] | None = None,
        raw_response: bool = False,
    ) -> str:
        self.sent_structured.append((agent_name, path, payload))
        if self.strict_registered_names and agent_name not in self.names:
            raise ValueError(f'피어 에이전트를 찾지 못했습니다: {agent_name}')
        if agent_name in self.failing_names:
            raise RuntimeError(f'{agent_name} is down')
        if (agent_name, path) in self.responses:
            return self.responses[(agent_name, path)]
        if raw_response and path == INVENTORY_LOOKUP_LOCAL_PREFIX:
            query = payload.get(QUERY, '')
            return json.dumps(
                {
                    'status': 'success',
                    'matched_row_count': 1,
                    'message': f'raw:{query}',
                },
                ensure_ascii=False,
            )
        return f'peer:{agent_name}:{path}'


def fake_agent(
    peers: FakePeers | None = None,
    agent_name: str = 'A',
    supplier_delivery_time_by_agent: dict[str, int] | None = None,
    inventory: FakeInventory | None = None,
) -> PartsMultiAgent:
    agent = PartsMultiAgent(
        agent_config(agent_name, supplier_delivery_time_by_agent)
    )
    agent.inventory = inventory or FakeInventory()
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

    async def test_structured_local_inventory_logs_from_bottleneck(
        self,
    ) -> None:
        agent = fake_agent(agent_name='B')

        with self.assertLogs('parts_multiagent.agent', level='INFO') as logs:
            result = await agent.invoke_structured(
                INVENTORY_LOOKUP_LOCAL_PREFIX,
                {QUERY: 'FLT-101 재고'},
            )

        logged = '\n'.join(logs.output)
        self.assertIn('raw:FLT-101 재고', result)
        self.assertIn('skill 실행 완료: agent=B', logged)
        self.assertIn('skill_id=재고조회', logged)
        self.assertIn('응답_에이전트=B', logged)

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
        self.assertEqual(agent.inventory.queries, ['FLT-101 재고'])
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

    async def test_structured_peer_inventory_does_not_log_each_peer_twice(
        self,
    ) -> None:
        peers = FakePeers(names=['B', 'C'])
        agent = fake_agent(peers)

        with self.assertLogs(level='INFO') as logs:
            result = await agent.invoke_structured(
                INVENTORY_LOOKUP_PEERS_PREFIX,
                {QUERY: 'FLT-101 재고'},
            )

        logged = '\n'.join(logs.output)
        self.assertIn('[B] 응답입니다.', result)
        self.assertIn('[C] 응답입니다.', result)
        self.assertIn('skill 실행 완료: agent=A', logged)
        self.assertIn('skill_id=전국재고조회', logged)
        self.assertIn('응답_에이전트=A', logged)
        self.assertIn('응답_에이전트=B', logged)
        self.assertIn('응답_에이전트=C', logged)

    async def test_structured_unknown_path_returns_clear_message(self) -> None:
        agent = fake_agent()

        with self.assertLogs('parts_multiagent.agent', level='WARNING') as logs:
            result = await agent.invoke_structured('/unknown', {QUERY: 'x'})

        self.assertIn('지원하지 않는 skill 요청', '\n'.join(logs.output))
        self.assertIn('지원하지 않는 요청입니다', result)

    async def test_structured_parse_failure_logs_warning(self) -> None:
        agent = fake_agent()

        with self.assertLogs('parts_multiagent.agent', level='WARNING') as logs:
            result = await agent.invoke_structured(
                INVENTORY_LOOKUP_LOCAL_PREFIX,
                {},
            )

        logged = '\n'.join(logs.output)
        self.assertIn('구조화 요청 해석 실패', logged)
        self.assertIn('skill_id=재고조회', logged)
        self.assertIn('구조화 요청 해석 실패', result)

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
        peers = FakePeers(
            names=['B', 'C'],
            responses={
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":1,"message":"[inventory] 일치한 행 수: 1\\n부품번호,부품명,수량,가격(원)\\nFLT-101,Oil Filter,7,5000"}',
                (
                    'C',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":0,"message":"[inventory] 조건에 맞는 행이 없습니다."}',
            },
        )
        agent = fake_agent(
            peers,
            supplier_delivery_time_by_agent={'B': 4},
        )

        result = await agent.invoke_structured(
            LOCAL_STOCK_INBOUND_PREFIX,
            {
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )

        self.assertIn('주문 가능한 공급처 후보입니다.', result)
        self.assertIn('주문하시겠습니까? 공급처를 선택해 주세요.', result)
        self.assertIn(
            '[B] FLT-101 (Oil Filter) 3개 주문 가능 / 현재 재고 7개 / 단가 5,000원 / 총액 15,000원 / 후보 총액 15,000원 / 배송 4시간',
            result,
        )
        self.assertEqual(agent.inventory.queries, [])
        self.assertEqual(len(agent.inventory.stock_changes), 0)
        self.assertEqual(
            peers.sent_structured,
            [
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                    {
                        QUERY: 'FLT-101',
                    },
                ),
                (
                    'C',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                    {
                        QUERY: 'FLT-101',
                    },
                ),
            ],
        )

    async def test_structured_local_stock_inbound_response_includes_price_and_delivery_time(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B', 'C'],
            responses={
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":1,"message":"[inventory] 일치한 행 수: 1\\n부품번호,부품명,수량,가격(원)\\nFLT-101,Oil Filter,7,5000"}',
                (
                    'C',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":1,"message":"[inventory] 일치한 행 수: 1\\n부품번호,부품명,수량,가격(원)\\nFLT-101,Oil Filter,9,5200"}',
                },
        )
        agent = fake_agent(
            peers,
            supplier_delivery_time_by_agent={'B': 4, 'C': 24},
        )

        response = await agent.invoke_structured_response(
            LOCAL_STOCK_INBOUND_PREFIX,
            {
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(
            response_dict['order_candidates'][0][ESTIMATED_DELIVERY_TIME],
            '4시간',
        )
        self.assertEqual(
            response_dict['order_candidates'][1][ESTIMATED_DELIVERY_TIME],
            '24시간',
        )
        self.assertEqual(
            response_dict['order_candidates'][0][TOTAL_PRICE],
            15000,
        )
        self.assertEqual(
            response_dict['order_candidates'][0][ITEMS][0][UNIT_PRICE],
            5000,
        )
        self.assertEqual(
            response_dict['order_candidates'][0][ITEMS][0][TOTAL_PRICE],
            15000,
        )
        self.assertEqual(
            response_dict['order_candidates'][0][SUPPLIER_AGENT],
            'B',
        )

    async def test_structured_local_stock_inbound_with_structured_items_payload(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":1,"message":"[inventory] 일치한 행 수: 1\\n부품번호,부품명,수량,가격(원)\\nFLT-101,Oil Filter,7,5000"}',
            },
        )
        agent = fake_agent(
            peers,
            supplier_delivery_time_by_agent={'B': 4},
        )

        response = await agent.invoke_structured_response(
            LOCAL_STOCK_INBOUND_PREFIX,
            {
                RAW_ITEMS: 'FLT-101 3개',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict[STATUS], 'success')
        self.assertEqual(
            peers.sent_structured,
            [
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                    {QUERY: 'FLT-101'},
                ),
            ],
        )

    async def test_structured_local_stock_inbound_uses_delivery_time_fallback(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":1,"message":"[inventory] 일치한 행 수: 1\\n부품번호,부품명,수량,가격(원)\\nFLT-101,Oil Filter,7,5000"}',
            },
        )
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            LOCAL_STOCK_INBOUND_PREFIX,
            {
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(
            response_dict['order_candidates'][0][ESTIMATED_DELIVERY_TIME],
            '배송시간 확인 필요',
        )
        self.assertEqual(
            response_dict['order_candidates'][0][TOTAL_PRICE],
            15000,
        )
        self.assertIn('배송시간 확인 필요', response_dict['message'])

    async def test_structured_local_stock_inbound_omits_price_when_missing(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":1,"message":"[inventory] 일치한 행 수: 1\\n부품번호,부품명,수량\\nFLT-101,Oil Filter,7"}',
            },
        )
        agent = fake_agent(peers, supplier_delivery_time_by_agent={'B': 4})

        response = await agent.invoke_structured_response(
            LOCAL_STOCK_INBOUND_PREFIX,
            {
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertIsNone(response_dict['order_candidates'][0][TOTAL_PRICE])
        self.assertNotIn(
            UNIT_PRICE,
            response_dict['order_candidates'][0][ITEMS][0],
        )
        self.assertNotIn(
            TOTAL_PRICE,
            response_dict['order_candidates'][0][ITEMS][0],
        )

    async def test_structured_order_selection_calls_peer_stock_outbound(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    PEER_STOCK_OUTBOUND_PREFIX,
                ): json.dumps(
                    {
                        'status': 'success',
                        'order_id': 'a1b2c3d4e5',
                        'items_shipped': 0,
                        'message': '[inventory] 주문 접수 완료: 1건\n- FLT-101: 3개 주문 접수 (현재 재고: 7개, 상태: 결제대기)',
                    },
                    ensure_ascii=False,
                ),
            },
        )
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict[SUPPLIER_AGENT], 'B')
        self.assertEqual(
            response_dict[PAYMENT_URL],
            'https://pay.kakaopay.com/mock/parts-order',
        )
        self.assertEqual(response_dict[ORDER_ID], 'a1b2c3d4e5')
        self.assertIn('B 공급처 주문이 접수되었습니다.', response_dict['message'])
        self.assertIn('주문번호: a1b2c3d4e5', response_dict['message'])
        self.assertIn('[inventory] 주문 접수 완료: 1건', response_dict['message'])
        self.assertIn('주문 상태: 결제대기', response_dict['message'])
        self.assertEqual(response_dict[ITEMS_SHIPPED], 0)
        self.assertEqual(len(agent.inventory.stock_changes), 0)
        self.assertEqual(len(agent.inventory.local_pending_inbound_orders), 1)
        self.assertEqual(
            agent.inventory.local_pending_inbound_orders[0]['order_id'],
            'a1b2c3d4e5',
        )
        self.assertEqual(
            peers.sent_structured,
            [
                (
                    'B',
                    PEER_STOCK_OUTBOUND_PREFIX,
                    {
                        AGENT_NAME: 'B',
                        RAW_ITEMS: 'FLT-101 3',
                        ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
                    },
                ),
            ],
        )

    async def test_structured_order_selection_returns_peer_error(
        self,
    ) -> None:
        peers = FakePeers(names=[], failing_names={'B'})
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertEqual(response_dict[SUPPLIER_AGENT], 'B')
        self.assertIn('원격 출고 요청에 실패했습니다', response_dict['message'])
        self.assertEqual(agent.inventory.local_pending_inbound_orders, [])

    async def test_structured_order_selection_returns_error_when_local_pending_save_fails(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    PEER_STOCK_OUTBOUND_PREFIX,
                ): json.dumps(
                    {
                        'status': 'success',
                        'order_id': 'a1b2c3d4e5',
                        'items_shipped': 0,
                        'message': '[inventory] 주문 접수 완료: 1건',
                    },
                    ensure_ascii=False,
                ),
            },
        )
        inventory = FakeInventory(
            local_pending_inbound_order_result=(
                False,
                '로컬 결제대기 주문 저장 실패: order 워크시트 헤더가 올바르지 않습니다.',
            )
        )
        agent = fake_agent(peers, inventory=inventory)

        response = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertIn('로컬 결제대기 주문 저장 실패', response_dict['message'])
        self.assertEqual(len(agent.inventory.local_pending_inbound_orders), 1)

    async def test_peer_directory_refreshes_before_sending_to_unknown_agent(
        self,
    ) -> None:
        peer_directory = PeerDirectory(
            ['http://localhost:10002'],
            'A',
        )
        peer_card = AgentCard(
            name='B',
            description='warehouse B',
            url='http://localhost:10002',
            version='1.0.0',
            defaultInputModes=['application/json'],
            defaultOutputModes=['application/json'],
            capabilities=AgentCapabilities(),
            skills=[],
        )
        refresh_mock = AsyncMock(
            side_effect=lambda: _populate_peer_directory(peer_directory, peer_card)
        )
        send_message_response = SimpleNamespace(
            root=SendMessageSuccessResponse(
                result=Message(
                    role=Role.agent,
                    messageId='msg-1',
                    parts=[Part(root=TextPart(text='{"message":"ok"}'))],
                )
            )
        )

        with patch.object(peer_directory, 'refresh', refresh_mock):
            with patch(
                'parts_multiagent.domain.peer.peer_client.A2AClient'
            ) as mock_a2a_client:
                mock_a2a_client.return_value.send_message = AsyncMock(
                    return_value=send_message_response
                )

                result = await peer_directory.send_structured_message(
                    'B',
                    PEER_STOCK_OUTBOUND_PREFIX,
                    {
                        AGENT_NAME: 'B',
                        RAW_ITEMS: 'FLT-101 3',
                        ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
                    },
                )

        self.assertEqual(refresh_mock.await_count, 1)
        self.assertEqual(result, 'ok')

    async def test_structured_order_selection_returns_remote_error_response(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    PEER_STOCK_OUTBOUND_PREFIX,
                ): json.dumps(
                    {
                        'status': 'error',
                        'items_shipped': 0,
                        'message': 'DIFFCARR01 출고 수량이 현재 재고보다 큽니다',
                    },
                    ensure_ascii=False,
                ),
            },
        )
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [{PART: 'DIFFCARR01', QUANTITY: 1}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertEqual(response_dict[SUPPLIER_AGENT], 'B')
        self.assertEqual(response_dict[PAYMENT_URL], '')
        self.assertEqual(response_dict[ITEMS_SHIPPED], 0)
        self.assertIn('출고 수량이 현재 재고보다 큽니다', response_dict['message'])

    async def test_structured_order_selection_returns_error_for_invalid_remote_response(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                ('B', PEER_STOCK_OUTBOUND_PREFIX): 'not-json',
            },
        )
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertEqual(response_dict[SUPPLIER_AGENT], 'B')
        self.assertIn('원격 출고 응답을 해석하지 못했습니다.', response_dict['message'])

    async def test_structured_order_selection_returns_error_when_remote_success_missing_order_id(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    PEER_STOCK_OUTBOUND_PREFIX,
                ): json.dumps(
                    {
                        'status': 'success',
                        'items_shipped': 0,
                        'message': '[inventory] 주문 접수 완료: 1건',
                    },
                    ensure_ascii=False,
                ),
            },
        )
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertEqual(response_dict[SUPPLIER_AGENT], 'B')
        self.assertIn('order_id가 없습니다', response_dict['message'])

    async def test_structured_payment_completion_calls_specific_supplier_agent(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    PEER_PAYMENT_COMPLETION_PREFIX,
                ): json.dumps(
                    {
                        'status': 'success',
                        'message': '주문 o-1의 결제가 완료되었습니다.',
                        'order_id': 'o-1',
                        'updated_row': 3,
                    },
                    ensure_ascii=False,
                ),
            },
        )
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            PAYMENT_COMPLETION_PREFIX,
            {
                ORDER_ID: 'o-1',
                SUPPLIER_AGENT: 'B',
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'success')
        self.assertEqual(response_dict[ORDER_ID], 'o-1')
        self.assertEqual(response_dict['updated_row'], 3)
        self.assertEqual(response_dict['local_inventory_updated_count'], 1)
        self.assertEqual(response_dict['local_inventory_appended_count'], 0)
        self.assertEqual(response_dict['local_order_updated_count'], 1)
        self.assertEqual(
            agent.inventory.paid_inbound_orders,
            [{'order_id': 'o-1', 'agent_name': 'A'}],
        )
        self.assertEqual(
            peers.sent_structured,
            [
                (
                    'B',
                    PEER_PAYMENT_COMPLETION_PREFIX,
                    {ORDER_ID: 'o-1'},
                ),
            ],
        )

    async def test_structured_payment_completion_requires_supplier_agent(
        self,
    ) -> None:
        agent = fake_agent()

        response = await agent.invoke_structured_response(
            PAYMENT_COMPLETION_PREFIX,
            {
                ORDER_ID: 'o-2',
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict[STATUS], 'error')
        self.assertIn('구조화 요청 해석 실패', response_dict[MESSAGE])
        self.assertIn(SUPPLIER_AGENT, response_dict[MESSAGE])

    async def test_structured_payment_completion_returns_error_when_remote_call_fails(
        self,
    ) -> None:
        peers = FakePeers(names=['B'], failing_names={'B'})
        agent = fake_agent(peers)

        response = await agent.invoke_structured_response(
            PAYMENT_COMPLETION_PREFIX,
            {
                ORDER_ID: 'o-3',
                SUPPLIER_AGENT: 'B',
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertIn('원격 결제 완료 요청에 실패했습니다', response_dict['message'])
        self.assertEqual(response_dict[ORDER_ID], 'o-3')
        self.assertEqual(agent.inventory.paid_inbound_orders, [])

    async def test_structured_payment_completion_returns_error_when_local_apply_fails(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    PEER_PAYMENT_COMPLETION_PREFIX,
                ): json.dumps(
                    {
                        'status': 'success',
                        'message': '주문 o-9의 결제가 완료되었습니다.',
                        'order_id': 'o-9',
                        'updated_row': 7,
                    },
                    ensure_ascii=False,
                ),
            },
        )
        inventory = FakeInventory(
            paid_inbound_order_result=(
                False,
                '로컬 결제 확정 반영 실패: 결제대기 입고 주문 행을 찾을 수 없습니다: o-9',
                0,
                0,
                0,
            )
        )
        agent = fake_agent(peers, inventory=inventory)

        response = await agent.invoke_structured_response(
            PAYMENT_COMPLETION_PREFIX,
            {
                ORDER_ID: 'o-9',
                SUPPLIER_AGENT: 'B',
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertIn('로컬 결제 확정 반영 실패', response_dict['message'])
        self.assertEqual(response_dict[ORDER_ID], 'o-9')
        self.assertEqual(response_dict['local_inventory_updated_count'], 0)
        self.assertEqual(response_dict['local_inventory_appended_count'], 0)
        self.assertEqual(response_dict['local_order_updated_count'], 0)

    async def test_structured_peer_payment_completion_applies_local_outbound_order(
        self,
    ) -> None:
        agent = fake_agent(inventory=FakeInventory())

        response = await agent.invoke_structured_response(
            PEER_PAYMENT_COMPLETION_PREFIX,
            {
                ORDER_ID: 'o-11',
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'success')
        self.assertEqual(response_dict[ORDER_ID], 'o-11')
        self.assertEqual(response_dict['local_inventory_updated_count'], 1)
        self.assertEqual(response_dict['local_inventory_appended_count'], 0)
        self.assertEqual(response_dict['local_order_updated_count'], 1)
        self.assertEqual(
            agent.inventory.paid_outbound_orders,
            [{'order_id': 'o-11', 'agent_name': 'A'}],
        )
        self.assertEqual(agent.inventory.paid_inbound_orders, [])

    async def test_structured_peer_payment_completion_returns_error_when_local_apply_fails(
        self,
    ) -> None:
        inventory = FakeInventory(
            paid_outbound_order_result=(
                False,
                '로컬 결제 확정 반영 실패: 결제대기 출고 주문 행을 찾을 수 없습니다: o-12',
                0,
                0,
                0,
            ),
        )
        agent = fake_agent(inventory=inventory)

        response = await agent.invoke_structured_response(
            PEER_PAYMENT_COMPLETION_PREFIX,
            {
                ORDER_ID: 'o-12',
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertIn('로컬 결제 확정 반영 실패', response_dict['message'])
        self.assertEqual(response_dict[ORDER_ID], 'o-12')
        self.assertEqual(response_dict['local_inventory_updated_count'], 0)
        self.assertEqual(response_dict['local_inventory_appended_count'], 0)
        self.assertEqual(response_dict['local_order_updated_count'], 0)
        self.assertEqual(
            agent.inventory.paid_outbound_orders,
            [{'order_id': 'o-12', 'agent_name': 'A'}],
        )
        self.assertEqual(agent.inventory.paid_inbound_orders, [])

    async def test_structured_peer_stock_outbound_returns_error_when_stock_is_not_enough(
        self,
    ) -> None:
        peers = FakePeers(names=['B'])
        inventory = FakeInventory(
            pending_outbound_order_result=(
                'context',
                'DIFFCARR01 출고 수량이 현재 재고보다 큽니다: 요청 수량: 1개, 현재 재고: 0개',
                '',
            )
        )
        agent = fake_agent(peers, agent_name='B', inventory=inventory)

        response = await agent.invoke_structured_response(
            PEER_STOCK_OUTBOUND_PREFIX,
            {
                AGENT_NAME: 'B',
                ITEMS: [{PART: 'DIFFCARR01', QUANTITY: 1}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'error')
        self.assertEqual(response_dict[ITEMS_SHIPPED], 0)
        self.assertIn('출고 수량이 현재 재고보다 큽니다', response_dict['message'])
        self.assertEqual(agent.inventory.stock_changes, [])
        self.assertEqual(len(agent.inventory.pending_outbound_orders), 1)
        self.assertEqual(
            agent.inventory.pending_outbound_orders[0]['request_text'],
            'DIFFCARR01 1',
        )
        self.assertEqual(
            agent.inventory.pending_outbound_orders[0]['agent_name'],
            'B',
        )

    async def test_structured_peer_stock_outbound_registers_pending_order(
        self,
    ) -> None:
        peers = FakePeers(names=['B'])
        inventory = FakeInventory()
        agent = fake_agent(peers, agent_name='B', inventory=inventory)

        response = await agent.invoke_structured_response(
            PEER_STOCK_OUTBOUND_PREFIX,
            {
                AGENT_NAME: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(response)

        self.assertEqual(response_dict['status'], 'success')
        self.assertEqual(response_dict[ITEMS_SHIPPED], 0)
        self.assertIn('주문 접수 완료', response_dict['message'])
        self.assertIn('결제대기', response_dict['message'])
        self.assertEqual(agent.inventory.stock_changes, [])
        self.assertEqual(len(agent.inventory.pending_outbound_orders), 1)
        self.assertEqual(
            agent.inventory.pending_outbound_orders[0]['request_text'],
            'FLT-101 3',
        )
        self.assertEqual(
            agent.inventory.pending_outbound_orders[0]['agent_name'],
            'B',
        )

    async def test_structured_order_selection_requires_supplier_agent(
        self,
    ) -> None:
        agent = fake_agent()

        result = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
            },
        )
        response_dict = response_to_json_dict(result)

        self.assertEqual(response_dict[STATUS], 'error')
        self.assertIn('구조화 요청 해석 실패', response_dict[MESSAGE])
        self.assertIn(SUPPLIER_AGENT, response_dict[MESSAGE])

    async def test_structured_order_selection_requires_items(
        self,
    ) -> None:
        agent = fake_agent()

        result = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [],
            },
        )
        response_dict = response_to_json_dict(result)

        self.assertEqual(response_dict[STATUS], 'error')
        self.assertIn('구조화 요청 해석 실패', response_dict[MESSAGE])
        self.assertIn(ITEMS, response_dict[MESSAGE])

    async def test_structured_order_selection_requires_integer_quantity(
        self,
    ) -> None:
        agent = fake_agent()

        result = await agent.invoke_structured_response(
            ORDER_SELECTION_PREFIX,
            {
                SUPPLIER_AGENT: 'B',
                ITEMS: [{PART: 'FLT-101', QUANTITY: '3'}],
            },
        )
        response_dict = response_to_json_dict(result)

        self.assertEqual(response_dict[STATUS], 'error')
        self.assertIn('구조화 요청 해석 실패', response_dict[MESSAGE])
        self.assertIn(QUANTITY, response_dict[MESSAGE])

    async def test_structured_local_stock_inbound_logs_peer_with_source_agent(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":1,"message":"[inventory] 일치한 행 수: 1\\n부품번호,부품명,수량,가격(원)\\nFLT-101,Oil Filter,7,5000"}',
            },
        )
        agent = fake_agent(peers)

        with self.assertLogs(
            'parts_multiagent.domain.local_stock_inbound.handler',
            level='INFO',
        ) as logs:
            await agent.invoke_structured(
                LOCAL_STOCK_INBOUND_PREFIX,
                {
                    ITEMS: [{PART: 'FLT-101', QUANTITY: 3}],
                },
            )

        logged = '\n'.join(logs.output)
        self.assertIn('응답_에이전트=B', logged)
        self.assertIn(f'요청={INVENTORY_LOOKUP_LOCAL_PREFIX} FLT-101 3', logged)

    async def test_structured_local_stock_inbound_without_candidates_returns_error(
        self,
    ) -> None:
        peers = FakePeers(
            names=['B'],
            responses={
                (
                    'B',
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                ): '{"status":"success","matched_row_count":0,"message":"[inventory] 조건에 맞는 행이 없습니다."}',
            },
        )
        agent = fake_agent(peers)

        result = await agent.invoke_structured(
            LOCAL_STOCK_INBOUND_PREFIX,
            {
                ITEMS: [{PART: 'STARTMTR01', QUANTITY: 1}],
            },
        )

        self.assertIn('주문 가능한 공급처를 찾지 못했습니다.', result)
        self.assertEqual(agent.inventory.stock_changes, [])


if __name__ == '__main__':
    unittest.main()


# 테스트용 PeerDirectory 캐시를 갱신해 새로고침 이후 상태를 재현합니다.
def _populate_peer_directory(
    peer_directory: PeerDirectory,
    peer_card: AgentCard,
) -> list[str]:
    peer_directory.cards[peer_card.name] = peer_card
    peer_directory.urls_by_name[peer_card.name] = peer_card.url
    return []
