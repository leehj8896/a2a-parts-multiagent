from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from parts_multiagent.agent_messages import EMPTY_QUERY_MESSAGE
from parts_multiagent.domain.inventory_lookup_local.handler import (
    handle as handle_local_inventory_query,
)
from parts_multiagent.domain.inventory_lookup_peers.handler import (
    handle as handle_peer_inventory_query,
)
from parts_multiagent.domain.inventory_lookup_local.types.request import (
    LocalInventoryQueryRequest,
)
from parts_multiagent.domain.inventory_lookup_peers.types.request import (
    PeerInventoryQueryRequest,
)


class StubInventory:
    def __init__(self, result_text: str) -> None:
        self.result_text = result_text

    def query(self, question: str) -> tuple[str, str]:
        return "ignored-context", self.result_text


class StubPeers:
    def __init__(
        self,
        agent_names: list[str],
        responses_by_name: dict[str, str | Exception],
        refresh_errors: list[str] | None = None,
    ) -> None:
        self._agent_names = agent_names
        self._responses_by_name = responses_by_name
        self._refresh_errors = refresh_errors or []

    async def refresh(self) -> list[str]:
        return self._refresh_errors

    def agent_names(self) -> list[str]:
        return self._agent_names

    async def send_structured_message(
        self,
        agent_name: str,
        path: str,
        payload: dict[str, object],
        output_formats: list[str] | None = None,
        raw_response: bool = False,
    ) -> str:
        response = self._responses_by_name[agent_name]
        if isinstance(response, Exception):
            raise response
        return response


class InventoryQueryResponseTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_inventory_query_returns_minimal_response(self) -> None:
        agent = SimpleNamespace(
            inventory=StubInventory(
                "[부품재고] 일치한 검색어: STARTMTR01; 일치한 행 수: 1\n"
                "부품번호,부품명,수량\nSTARTMTR01,스타터 모터 어셈블리,5"
            )
        )

        response = await handle_local_inventory_query(
            agent,
            LocalInventoryQueryRequest(query="STARTMTR01"),
        )

        self.assertEqual(
            response.to_json_dict(),
            {
                "status": "success",
                "matched_row_count": 1,
                "message": (
                    "[부품재고] 일치한 검색어: STARTMTR01; 일치한 행 수: 1\n"
                    "부품번호,부품명,수량\nSTARTMTR01,스타터 모터 어셈블리,5"
                ),
            },
        )

    async def test_local_inventory_query_empty_query_returns_error(self) -> None:
        agent = SimpleNamespace(inventory=StubInventory("unused"))

        response = await handle_local_inventory_query(
            agent,
            LocalInventoryQueryRequest(query=""),
        )

        self.assertEqual(
            response.to_json_dict(),
            {
                "status": "error",
                "matched_row_count": 0,
                "message": EMPTY_QUERY_MESSAGE,
            },
        )

    async def test_peer_inventory_query_returns_minimal_nested_response(self) -> None:
        local_result_text = (
            "[부품재고] 일치한 검색어: STARTMTR01; 일치한 행 수: 1\n"
            "부품번호,부품명,수량\nSTARTMTR01,스타터 모터 어셈블리,5"
        )
        peer_response_text = (
            "[부품재고] 일치한 검색어: STARTMTR01; 일치한 행 수: 2\n"
            "부품번호,부품명,수량\nSTARTMTR01,스타터 모터 어셈블리,3"
        )
        peer_response_json = json.dumps(
            {
                "status": "success",
                "matched_row_count": 2,
                "message": peer_response_text,
            },
            ensure_ascii=False,
        )
        agent = SimpleNamespace(
            config=SimpleNamespace(agent_name="A"),
            inventory=StubInventory(local_result_text),
            peers=StubPeers(["B"], {"B": peer_response_json}),
        )

        response = await handle_peer_inventory_query(
            agent,
            PeerInventoryQueryRequest(query="STARTMTR01"),
        )

        self.assertEqual(
            response.to_json_dict(),
            {
                "status": "success",
                "local_result": {
                    "agent_name": "A",
                    "matched_row_count": 1,
                    "message": local_result_text,
                },
                "peer_results": [
                    {
                        "agent_name": "B",
                        "status": "success",
                        "matched_row_count": 2,
                        "message": peer_response_text,
                        "error_message": "",
                    }
                ],
                "message": (
                    "## 내 재고 조회 (A)\n\n"
                    f"{local_result_text}\n\n"
                    "## 다른 agent 조회\n\n"
                    f"[B] 응답입니다.\n\n{peer_response_text}"
                ),
            },
        )

    async def test_peer_inventory_query_includes_peer_failure(self) -> None:
        agent = SimpleNamespace(
            config=SimpleNamespace(agent_name="A"),
            inventory=StubInventory("[부품재고] 조건에 맞는 행이 없습니다."),
            peers=StubPeers(["B"], {"B": RuntimeError("boom")}),
        )

        response = await handle_peer_inventory_query(
            agent,
            PeerInventoryQueryRequest(query="UNKNOWN"),
        )

        self.assertEqual(response.peer_results[0].status, "error")
        self.assertEqual(response.peer_results[0].matched_row_count, 0)
        self.assertIn("RuntimeError: boom", response.peer_results[0].error_message)
        self.assertIn("RuntimeError: boom", response.message)

    async def test_peer_inventory_query_logs_each_agent_with_source_agent(self) -> None:
        local_result_text = (
            "[부품재고] 일치한 검색어: STARTMTR01; 일치한 행 수: 1\n"
            "부품번호,부품명,수량\nSTARTMTR01,스타터 모터 어셈블리,5"
        )
        peer_response_text = (
            "[부품재고] 일치한 검색어: STARTMTR01; 일치한 행 수: 2\n"
            "부품번호,부품명,수량\nSTARTMTR01,스타터 모터 어셈블리,3"
        )
        peer_response_json = json.dumps(
            {
                "status": "success",
                "matched_row_count": 2,
                "message": peer_response_text,
            },
            ensure_ascii=False,
        )
        agent = SimpleNamespace(
            config=SimpleNamespace(agent_name="A"),
            inventory=StubInventory(local_result_text),
            peers=StubPeers(["B"], {"B": peer_response_json}),
        )

        with self.assertLogs(
            "parts_multiagent.domain.inventory_lookup_peers.handler",
            level="INFO",
        ) as logs:
            await handle_peer_inventory_query(
                agent,
                PeerInventoryQueryRequest(query="STARTMTR01"),
            )

        logged = "\n".join(logs.output)
        self.assertIn("응답_에이전트=A", logged)
        self.assertIn("응답_에이전트=B", logged)
        self.assertIn("질의=STARTMTR01", logged)


if __name__ == "__main__":
    unittest.main()
