from __future__ import annotations

import logging
import re

from dataclasses import dataclass
from typing import Any

import httpx

from .config import DEFAULT_SKILL_ID
from .constants.routing import build_route_prompt
from .constants.summarizing import build_summary_prompt


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteDecision:
    route: str
    target_agent_name: str | None
    skill_id: str
    task: str
    reason: str

    @classmethod
    def local(cls, task: str, reason: str = 'fallback to local CSV query'):
        return cls(
            route='local',
            target_agent_name=None,
            skill_id=DEFAULT_SKILL_ID,
            task=task,
            reason=reason,
        )


class LocalLlmClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

    async def choose_route(
        self,
        query: str,
        local_agent: dict[str, Any],
        peer_agents: list[dict[str, Any]],
    ) -> RouteDecision:
        prompt = self._route_prompt(query, local_agent, peer_agents)
        _log_llm_block('LLM ROUTE PROMPT', prompt)
        try:
            content = await self._chat(prompt, temperature=0)
            _log_llm_block('LLM ROUTE RESPONSE', content)
            raw = self._extract_json(content)
            route = raw.get('route', 'local')
            if route not in {'local', 'remote'}:
                route = 'local'
            return RouteDecision(
                route=route,
                target_agent_name=raw.get('target_agent_name'),
                skill_id=raw.get('skill_id') or DEFAULT_SKILL_ID,
                task=raw.get('task') or query,
                reason=raw.get('reason') or 'LLM routing decision',
            )
        except Exception as exc:
            logger.warning(
                'LLM route request failed: %s: %s',
                type(exc).__name__,
                exc,
            )
            return RouteDecision.local(
                query, f'LLM routing failed: {type(exc).__name__}: {exc}'
            )

    async def summarize_answer(
        self,
        query: str,
        csv_context: str,
        raw_result: str,
    ) -> str:
        prompt = build_summary_prompt(query, csv_context, raw_result)
        _log_llm_block('LLM ANSWER PROMPT', prompt)
        try:
            content = await self._chat(prompt, temperature=0.2)
            _log_llm_block('LLM ANSWER RESPONSE', content)
            return content
        except Exception as exc:
            logger.warning(
                'LLM answer request failed: %s: %s',
                type(exc).__name__,
                exc,
            )
            return raw_result

    async def _chat(self, prompt: str, temperature: float) -> str:
        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f'{self.base_url}/chat/completions', json=payload
            )
            response.raise_for_status()
            data = response.json()
        return data['choices'][0]['message']['content']

    def _route_prompt(
        self,
        query: str,
        local_agent: dict[str, Any],
        peer_agents: list[dict[str, Any]],
    ) -> str:
        return build_route_prompt(
            query=query,
            local_agent=local_agent,
            peer_agents=peer_agents,
            skill_id=DEFAULT_SKILL_ID,
        )

    def _extract_json(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            return json.loads(stripped)
        match = re.search(r'\{.*\}', stripped, re.DOTALL)
        if not match:
            raise ValueError('LLM response did not include JSON')
        return json.loads(match.group(0))


def _log_llm_block(title: str, text: str) -> None:
    logger.info('\n%s\n%s\n%s\n%s', '=' * 72, title, text.strip(), '=' * 72)
