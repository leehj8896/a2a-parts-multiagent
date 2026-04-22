from __future__ import annotations

import uuid

from typing import Any

import httpx

from a2a.client import A2AClient, A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageSuccessResponse,
    Task,
)


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
        summaries = []
        for name, card in self.cards.items():
            summaries.append(
                {
                    'name': name,
                    'description': card.description,
                    'skills': [
                        {
                            'id': skill.id,
                            'name': skill.name,
                            'description': skill.description,
                            'tags': skill.tags,
                        }
                        for skill in card.skills
                    ],
                }
            )
        return summaries

    def agent_names(self) -> list[str]:
        return sorted(self.cards)

    async def send_message(self, agent_name: str, text: str) -> str:
        if agent_name == self.local_agent_name:
            raise ValueError(
                f'Refusing to send a remote request to self: {agent_name}'
            )
        if agent_name not in self.cards:
            raise ValueError(f'Peer agent not found: {agent_name}')

        message_id = uuid.uuid4().hex
        payload = {
            'message': {
                'role': 'user',
                'parts': [{'type': 'text', 'text': text}],
                'messageId': message_id,
            }
        }
        request = SendMessageRequest(
            id=message_id,
            params=MessageSendParams.model_validate(payload),
        )
        async with httpx.AsyncClient(timeout=30) as client:
            a2a_client = A2AClient(
                client,
                self.cards[agent_name],
                url=self.urls_by_name[agent_name],
            )
            response = await a2a_client.send_message(request)

        if not isinstance(response.root, SendMessageSuccessResponse):
            return f'Peer {agent_name} returned a non-success response.'
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
