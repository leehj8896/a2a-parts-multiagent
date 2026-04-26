from __future__ import annotations

import json
import uuid

from typing import Any

import httpx

from a2a.client import A2AClient, A2ACardResolver
from a2a.types import (
    AgentCard,
    DataPart,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    SendMessageSuccessResponse,
    Task,
)
from parts_multiagent.domain.peer.constants.agent_summary_keys import (
    DESCRIPTION,
    NAME,
    SKILLS,
    SKILL_DESCRIPTION,
    SKILL_ID,
    SKILL_NAME,
    SKILL_TAGS,
)
from parts_multiagent.domain.peer_stock_outbound.constants.response_keys import (
    MESSAGE,
)
from parts_multiagent.utils.constants.structured_payload_keys import PATH, PAYLOAD


class PeerDirectory:
    def __init__(self, peer_urls: list[str], local_agent_name: str) -> None:
        self.peer_urls = peer_urls
        self.local_agent_name = local_agent_name
        self.cards: dict[str, AgentCard] = {}
        self.urls_by_name: dict[str, str] = {}

    async def refresh(self) -> list[str]:
        errors = []
        self.cards = {}
        self.urls_by_name = {}
        async with httpx.AsyncClient(timeout=10) as client:
            for url in self.peer_urls:
                try:
                    card = await A2ACardResolver(client, url).get_agent_card()
                    if card.name == self.local_agent_name:
                        continue
                    self.cards[card.name] = card
                    self.urls_by_name[card.name] = url
                except Exception as exc:
                    errors.append(f'{url}: {type(exc).__name__}: {exc}')
        return errors

    def agent_summaries(self) -> list[dict[str, Any]]:
        # 피어 AgentCard 정보를 요약해 LLM 프롬프트 입력 형태로 반환합니다.
        summaries = []
        for name, card in self.cards.items():
            summaries.append(
                {
                    NAME: name,
                    DESCRIPTION: card.description,
                    SKILLS: [
                        {
                            SKILL_ID: skill.id,
                            SKILL_NAME: skill.name,
                            SKILL_DESCRIPTION: skill.description,
                            SKILL_TAGS: skill.tags,
                        }
                        for skill in card.skills
                    ],
                }
            )
        return summaries

    def agent_names(self) -> list[str]:
        return sorted(self.cards)

    async def send_structured_message(
        self,
        agent_name: str,
        path: str,
        payload: dict[str, Any],
        output_formats: list[str] | None = None,
        raw_response: bool = False,
    ) -> str:
        """구조화 요청(DataPart)을 전송하고 응답을 받습니다.
        
        Args:
            agent_name: 대상 에이전트 이름
            path: 요청 경로 (예: "/피어출고요청")
            payload: 구조화 요청 페이로드
            output_formats: 수용 가능한 출력 형식. 기본값: ["application/json"]
        
        Returns:
            응답 텍스트 (JSON 문자열)
        """
        if output_formats is None:
            output_formats = ["application/json"]
        
        envelope = {PATH: path, PAYLOAD: payload}
        parts = [Part(root=DataPart(data=envelope))]
        response_text = await self._send_parts(
            agent_name,
            parts,
            accepted_output_modes=output_formats,
        )
        if raw_response:
            return response_text
        return self._display_text_from_structured_response(response_text)

    async def _send_parts(self, agent_name: str, parts: list[Part], accepted_output_modes: list[str] | None = None) -> str:
        """내부 메서드: Part 목록을 전송합니다.
        
        Args:
            agent_name: 대상 에이전트 이름
            parts: 전송할 Part 목록
            accepted_output_modes: 수용 가능한 출력 형식. 기본값: ["text"]
        """
        if accepted_output_modes is None:
            accepted_output_modes = ["application/json"]
        
        if agent_name == self.local_agent_name:
            raise ValueError(
                f'자기 자신에게 원격 요청을 보낼 수 없습니다: {agent_name}'
            )
        if agent_name not in self.cards:
            peer_errors = await self.refresh()
            if agent_name not in self.cards:
                errors = '\n'.join(f'- {error}' for error in peer_errors)
                suffix = f'\n{errors}' if errors else ''
                raise ValueError(
                    f'피어 에이전트를 찾지 못했습니다: {agent_name}{suffix}'
                )

        message_id = uuid.uuid4().hex
        message = Message(role=Role.user, parts=parts, message_id=message_id)
        params = MessageSendParams(
            message=message,
            configuration=MessageSendConfiguration(
                accepted_output_modes=accepted_output_modes
            ),
        )
        request = SendMessageRequest(
            id=message_id,
            params=params,
        )
        async with httpx.AsyncClient(timeout=30) as client:
            a2a_client = A2AClient(
                client,
                self.cards[agent_name],
                url=self.urls_by_name[agent_name],
            )
            response = await a2a_client.send_message(request)

        if not isinstance(response.root, SendMessageSuccessResponse):
            return f'피어 {agent_name}이 성공 응답이 아닌 응답을 반환했습니다.'
        result = response.root.result
        if isinstance(result, Task):
            return self._task_text(result)
        return '\n'.join(self._parts_text(getattr(result, 'parts', [])))

    def _task_text(self, task: Task) -> str:
        texts = []
        for artifact in task.artifacts or []:
            texts.extend(self._parts_text(artifact.parts))
        if not texts and task.status and task.status.message:
            texts.extend(self._parts_text(task.status.message.parts))
        return '\n'.join(texts) if texts else str(task)

    def _parts_text(self, parts: list[Any]) -> list[str]:
        texts = []
        for part in parts or []:
            if getattr(part, 'type', None) == 'text':
                texts.append(part.text)
                continue
            root = getattr(part, 'root', None)
            if root is not None and getattr(root, 'text', None):
                texts.append(root.text)
        return texts

    # 구조화 응답 JSON에서 사용자 표시용 message를 우선 추출합니다.
    def _display_text_from_structured_response(self, response_text: str) -> str:
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            return response_text
        if not isinstance(response_data, dict):
            return response_text
        message = response_data.get(MESSAGE)
        return message if isinstance(message, str) and message else response_text
