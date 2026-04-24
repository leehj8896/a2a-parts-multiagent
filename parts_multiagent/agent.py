from __future__ import annotations

import asyncio
import logging

from .command_registry import COMMANDS
from .config import PartsAgentConfig
from .constants.prefixes import (
    INVENTORY_LOOKUP_LOCAL_PREFIX,
)
from .constants.structured_payload_keys import QUERY
from .google_sheet_inventory import GoogleSheetConfig, GoogleSheetInventory
from .inventory_log import log_inventory_response
from .peer_client import PeerDirectory
from .structured_requests import build_request_from_payload


logger = logging.getLogger(__name__)


class PartsMultiAgent:
    def __init__(self, config: PartsAgentConfig) -> None:
        self.config = config
        self.inventory = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file=(
                    config.google_sheet.service_account_file
                ),
                spreadsheet_id=config.google_sheet.spreadsheet_id,
                inventory_worksheet=config.google_sheet.inventory_worksheet,
                order_worksheet=config.google_sheet.order_worksheet,
                inventory_headers=config.google_sheet.inventory_headers,
            )
        )
        self.peers = PeerDirectory(
            config.peer_agent_urls, config.agent_name
        )

    # 구조화 요청(DataPart)의 path/payload로 명령을 해석해 실행합니다.
    async def invoke_structured(self, path: str, payload: dict[str, object]) -> str:
        # path에서 "/" prefix 제거하고 skill_id로 조회
        skill_id = path.lstrip('/')
        command = COMMANDS.get(skill_id)
        if command is None:
            return f'지원하지 않는 요청입니다: {path}'

        try:
            request = build_request_from_payload(skill_id, payload)
        except Exception as exc:
            return f'구조화 요청 해석 실패: {type(exc).__name__}: {exc}'

        response = await command.handler(self, request)
        return str(response)

    # 피어 에이전트들에게 구조화 요청을 병렬로 전송하고 결과를 합쳐 반환합니다.
    async def query_peer_agents(
        self,
        task: str,
        peer_errors: list[str],
    ) -> str:
        peer_names = self.peers.agent_names()
        if not peer_names:
            answer = '## 다른 agent 조회\n\n조회 가능한 다른 agent가 없습니다.'
            if peer_errors:
                answer = self._append_peer_errors(answer, peer_errors)
            return answer

        peer_results = await asyncio.gather(
            *[
                self.peers.send_structured_message(
                    peer_name,
                    INVENTORY_LOOKUP_LOCAL_PREFIX,
                    {QUERY: task},
                )
                for peer_name in peer_names
            ],
            return_exceptions=True,
        )

        sections = []
        for peer_name, peer_result in zip(
            peer_names, peer_results, strict=True
        ):
            if isinstance(peer_result, Exception):
                sections.append(
                    f'[{peer_name}] 요청 실패: '
                    f'{type(peer_result).__name__}: {peer_result}'
                )
                continue
            log_inventory_response(
                logger=logger,
                local_agent=self.config.agent_name,
                source_agent=peer_name,
                query=task,
                response=peer_result,
            )
            sections.append(f'[{peer_name}] 응답입니다.\n\n{peer_result}')

        answer = '## 다른 agent 조회\n\n' + '\n\n'.join(sections)
        if peer_errors:
            answer = self._append_peer_errors(answer, peer_errors)
        return answer

    def _append_peer_errors(self, answer: str, peer_errors: list[str]) -> str:
        return (
            f'{answer}\n\n'
            '참고: 일부 peer agent의 AgentCard를 가져오지 못했습니다.\n'
            + '\n'.join(f'- {error}' for error in peer_errors)
        )
