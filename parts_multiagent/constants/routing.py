from __future__ import annotations

import json

from typing import Any


ROUTE_PROMPT_TEMPLATE = """
A2A LAN Google Sheets 멀티 에이전트 시스템에서 사용자의 재고 질문을 라우팅합니다.

아래 스키마와 정확히 같은 JSON만 반환하세요:
{{
  "route": "local|remote",
  "target_agent_name": "string|null",
  "skill_id": "{skill_id}",
  "task": "string",
  "reason": "string"
}}

규칙:
- 질문을 로컬 에이전트가 답할 수 있거나 명확히 일치하는 피어가 없으면 "local"을 사용하세요.
- 사용자가 다른 창고/장치/에이전트에 대해 묻거나, 피어 에이전트의 설명/이름이 명확히 일치할 때만 "remote"를 사용하세요.
- route가 "remote"이면 target_agent_name은 피어 에이전트 이름 중 하나와 정확히 일치해야 합니다.
- task는 선택한 에이전트가 단독으로 처리할 수 있는 완결된 요청이어야 합니다.

로컬 에이전트:
{local_agent}

피어 에이전트:
{peer_agents}

사용자 질문:
{query}
"""


def build_route_prompt(
    query: str,
    local_agent: dict[str, Any],
    peer_agents: list[dict[str, Any]],
    skill_id: str,
) -> str:
    return ROUTE_PROMPT_TEMPLATE.format(
        query=query,
        local_agent=json.dumps(local_agent, ensure_ascii=False),
        peer_agents=json.dumps(peer_agents, ensure_ascii=False),
        skill_id=skill_id,
    )
