from __future__ import annotations

import asyncio
import logging

from .config import PartsAgentConfig
from .google_sheet_inventory import GoogleSheetConfig, GoogleSheetInventory
from .inventory_log import log_inventory_response
from .llm_client import LocalLlmClient
from .peer_client import PeerDirectory


logger = logging.getLogger(__name__)
LOCAL_ONLY_PREFIX = '__PARTS_MULTIAGENT_LOCAL_ONLY__'


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
        local_only_task = self._local_only_task_from(query)
        if local_only_task is not None:
            return await self._query_local(local_only_task, local_only_task)

        peer_errors = await self.peers.refresh()
        local_summary = {
            'name': self.config.agent_name,
            'description': self.config.agent_description,
            'data': self.inventory.describe(),
        }
        decision = await self.llm.choose_route(
            query=query,
            local_agent=local_summary,
            peer_agents=self.peers.agent_summaries(),
        )

        if decision.route == 'remote' and decision.target_agent_name:
            try:
                peer_answer = await self.peers.send_message(
                    decision.target_agent_name,
                    self._local_only_message(decision.task),
                )
                log_inventory_response(
                    logger=logger,
                    local_agent=self.config.agent_name,
                    source_agent=decision.target_agent_name,
                    query=decision.task,
                    response=peer_answer,
                )
                return (
                    f'[{decision.target_agent_name}] 응답입니다.\n\n'
                    f'{peer_answer}'
                )
            except Exception as exc:
                errors = '\n'.join(peer_errors) if peer_errors else 'none'
                return (
                    f'원격 agent 요청에 실패했습니다: '
                    f'{decision.target_agent_name}\n'
                    f'오류: {type(exc).__name__}: {exc}\n'
                    f'Peer discovery errors: {errors}'
                )

        return await self._query_all_agents(
            query, decision.task or query, peer_errors
        )

    async def _query_all_agents(
        self,
        query: str,
        task: str,
        peer_errors: list[str],
    ) -> str:
        peer_names = self.peers.agent_names()
        results = await asyncio.gather(
            self._query_local(query, task),
            *[
                self.peers.send_message(
                    peer_name, self._local_only_message(task)
                )
                for peer_name in peer_names
            ],
            return_exceptions=True,
        )
        local_result, *peer_results = results

        if isinstance(local_result, Exception):
            sections = [
                f'[{self.config.agent_name}] 요청 실패: '
                f'{type(local_result).__name__}: {local_result}'
            ]
        else:
            sections = [
                f'[{self.config.agent_name}] 응답입니다.\n\n{local_result}'
            ]
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

        answer = '\n\n'.join(sections)
        if peer_errors:
            answer = (
                f'{answer}\n\n'
                '참고: 일부 peer agent의 AgentCard를 가져오지 못했습니다.\n'
                + '\n'.join(f'- {error}' for error in peer_errors)
            )
        return answer

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

    def _local_only_message(self, task: str) -> str:
        return f'{LOCAL_ONLY_PREFIX}\n{task}'

    def _local_only_task_from(self, query: str) -> str | None:
        if not query.startswith(LOCAL_ONLY_PREFIX):
            return None
        return query.removeprefix(LOCAL_ONLY_PREFIX).strip()
