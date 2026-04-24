from __future__ import annotations

import json
import logging
import re

from dataclasses import dataclass
from typing import Any

import httpx

from .config import DEFAULT_SKILL_ID
from .constants.routing import build_route_prompt
from .constants.stock_inbound_extraction import (
    build_stock_inbound_extraction_prompt,
)
from .constants.summarizing import build_summary_prompt
from .stock_inbound.types import ExtractedStockItem, StockInboundExtraction


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteDecision:
    route: str
    target_agent_name: str | None
    skill_id: str
    task: str
    reason: str

    @classmethod
    def local(
        cls,
        task: str,
        reason: str = '로컬 Google Sheet 조회로 대체',
    ):
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
        _log_llm_block('LLM 라우팅 프롬프트', prompt)
        try:
            content = await self._chat(prompt, temperature=0)
            _log_llm_block('LLM 라우팅 응답', content)
            raw = self._extract_json(content)
            route = raw.get('route', 'local')
            if route not in {'local', 'remote'}:
                route = 'local'
            return RouteDecision(
                route=route,
                target_agent_name=raw.get('target_agent_name'),
                skill_id=raw.get('skill_id') or DEFAULT_SKILL_ID,
                task=raw.get('task') or query,
                reason=raw.get('reason') or 'LLM 라우팅 결정',
            )
        except Exception as exc:
            logger.warning(
                'LLM 라우팅 요청에 실패했습니다: %s: %s',
                type(exc).__name__,
                exc,
            )
            return RouteDecision.local(
                query, f'LLM 라우팅 실패: {type(exc).__name__}: {exc}'
            )

    async def summarize_answer(
        self,
        query: str,
        csv_context: str,
        raw_result: str,
    ) -> str:
        prompt = build_summary_prompt(query, csv_context, raw_result)
        _log_llm_block('LLM 답변 프롬프트', prompt)
        try:
            content = await self._chat(prompt, temperature=0.2)
            _log_llm_block('LLM 답변 응답', content)
            return content
        except Exception as exc:
            logger.warning(
                'LLM 답변 요청에 실패했습니다: %s: %s',
                type(exc).__name__,
                exc,
            )
            return raw_result

    async def extract_stock_inbound(
        self,
        query: str,
        peer_agents: list[dict[str, Any]],
    ) -> StockInboundExtraction:
        prompt = build_stock_inbound_extraction_prompt(query, peer_agents)
        _log_llm_block('LLM 입고 추출 프롬프트', prompt)
        content = await self._chat(prompt, temperature=0)
        _log_llm_block('LLM 입고 추출 응답', content)
        raw = self._extract_json(content)

        target_agent_name = raw.get('target_agent_name')
        if target_agent_name is not None and not isinstance(
            target_agent_name, str
        ):
            raise ValueError('target_agent_name은 문자열 또는 null이어야 합니다.')

        raw_items = raw.get('items')
        if not isinstance(raw_items, list):
            raise ValueError('items는 배열이어야 합니다.')

        items: list[ExtractedStockItem] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise ValueError('items 배열 요소는 객체여야 합니다.')
            part = raw_item.get('part')
            quantity = raw_item.get('quantity')
            if not isinstance(part, str) or not part.strip():
                raise ValueError('part는 비어 있지 않은 문자열이어야 합니다.')
            if not isinstance(quantity, int):
                raise ValueError('quantity는 정수여야 합니다.')
            items.append(
                ExtractedStockItem(part=part.strip(), quantity=quantity)
            )

        reason = raw.get('reason') or ''
        if not isinstance(reason, str):
            raise ValueError('reason은 문자열이어야 합니다.')

        return StockInboundExtraction(
            target_agent_name=target_agent_name,
            items=items,
            reason=reason.strip(),
        )

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
            raise ValueError('LLM 응답에 JSON이 포함되어 있지 않습니다')
        return json.loads(match.group(0))


def _log_llm_block(title: str, text: str) -> None:
    logger.info('\n%s\n%s\n%s\n%s', '=' * 72, title, text.strip(), '=' * 72)
