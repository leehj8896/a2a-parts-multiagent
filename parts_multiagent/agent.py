from __future__ import annotations

import asyncio
import logging

from .config import PartsAgentConfig
from .constants.prefixes import LOCAL_AGENT_PREFIX, PEER_AGENTS_PREFIX
from .google_sheet_inventory import GoogleSheetConfig, GoogleSheetInventory
from .inventory_log import log_inventory_response
from .llm_client import LocalLlmClient
from .peer_client import PeerDirectory


logger = logging.getLogger(__name__)
EMPTY_QUERY_MESSAGE = '조회할 질문을 입력해주세요.'


class PartsMultiAgent:
    def __init__(self, config: PartsAgentConfig) -> None:
        self.config = config
        self.inventory = GoogleSheetInventory(
            GoogleSheetConfig(
                service_account_file=(
                    config.google_sheet.service_account_file
                ),
                spreadsheet_id=config.google_sheet.spreadsheet_id,
                worksheet=config.google_sheet.worksheet,
            )
        )
        self.llm = LocalLlmClient(config.llm_base_url, config.llm_model)
        self.peers = PeerDirectory(
            config.peer_agent_urls, config.agent_name
        )

    async def invoke(self, query: str) -> str:
        query = query.strip()
        local_task = self._task_from_prefix(query, LOCAL_AGENT_PREFIX)
        if local_task is not None:
            if not local_task:
                return EMPTY_QUERY_MESSAGE
            return await self._query_local(local_task, local_task)

        peer_task = self._task_from_prefix(query, PEER_AGENTS_PREFIX)
        if peer_task is not None:
            if not peer_task:
                return EMPTY_QUERY_MESSAGE
            peer_errors = await self.peers.refresh()
            return await self._query_peer_agents(peer_task, peer_errors)

        if not query:
            return EMPTY_QUERY_MESSAGE

        return await self._query_local_and_peer_agents(query, query)

    async def _query_local_and_peer_agents(
        self,
        query: str,
        task: str,
    ) -> str:
        local_section = await self._query_local_agent_section(query, task)
        peer_errors = await self.peers.refresh()
        peer_section = await self._query_peer_agents(task, peer_errors)
        return f'## 내 agent 조회\n\n{local_section}\n\n{peer_section}'

    async def _query_peer_agents(
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
                self.peers.send_message(
                    peer_name, self._peer_local_message(task)
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

        answer = f'## 다른 agent 조회\n\n' + '\n\n'.join(sections)
        if peer_errors:
            answer = self._append_peer_errors(answer, peer_errors)
        return answer

    async def _query_local_agent_section(self, query: str, task: str) -> str:
        try:
            local_result = await self._query_local(query, task)
        except Exception as exc:
            return (
                f'[{self.config.agent_name}] 요청 실패: '
                f'{type(exc).__name__}: {exc}'
            )
        return f'[{self.config.agent_name}] 응답입니다.\n\n{local_result}'

    async def _query_local(self, query: str, task: str) -> str:
        context, raw_result = self.inventory.query(task)
        log_inventory_response(
            logger=logger,
            local_agent=self.config.agent_name,
            source_agent=self.config.agent_name,
            query=task,
            response=raw_result,
        )
        return await self.llm.summarize_answer(query, context, raw_result)

    def _peer_local_message(self, task: str) -> str:
        return f'{LOCAL_AGENT_PREFIX} {task}'

    def _task_from_prefix(self, query: str, prefix: str) -> str | None:
        if query == prefix:
            return ''
        if query.startswith(prefix) and query[len(prefix)].isspace():
            return query[len(prefix) :].strip()
        return None

    def _append_peer_errors(self, answer: str, peer_errors: list[str]) -> str:
        return (
            f'{answer}\n\n'
            '참고: 일부 peer agent의 AgentCard를 가져오지 못했습니다.\n'
            + '\n'.join(f'- {error}' for error in peer_errors)
        )
