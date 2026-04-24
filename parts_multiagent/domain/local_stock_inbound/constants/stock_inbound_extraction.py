from __future__ import annotations

import json

from typing import Any

from parts_multiagent.utils.constants.llm_json_keys import REASON, TARGET_AGENT_NAME
from parts_multiagent.utils.constants.structured_payload_keys import (
    ITEMS,
    PART,
    QUANTITY,
)

STOCK_INBOUND_PARSE_ERROR = (
    '입고 요청을 보낼 agent 이름과 품목/수량을 명확히 입력해주세요.'
)
STOCK_INBOUND_LLM_FAILURE_PREFIX = '입고 요청 해석 실패'

STOCK_INBOUND_EXTRACTION_SCHEMA = {
    TARGET_AGENT_NAME: 'string|null',
    ITEMS: [{PART: 'string', QUANTITY: 'integer'}],
    REASON: 'string',
}

STOCK_INBOUND_EXTRACTION_PROMPT_TEMPLATE = """
A2A LAN Google Sheets 멀티 에이전트 시스템에서 사용자의 입고 요청을 구조화합니다.

아래 스키마와 정확히 같은 JSON만 반환하세요:
{schema}

규칙:
- target_agent_name은 반드시 아래 peer agent 목록 중 하나와 정확히 일치해야 합니다.
- items에는 사용자가 해당 peer agent로부터 가져오려는 품목과 수량만 넣으세요.
- quantity는 1 이상의 정수여야 합니다.
- 확신할 수 없으면 target_agent_name을 null로 두거나 items를 빈 배열로 두고
  reason에 부족한 정보를 적으세요.
- JSON 외의 설명 문장은 절대 출력하지 마세요.

피어 에이전트:
{peer_agents}

사용자 요청:
{query}
"""


def build_stock_inbound_extraction_prompt(
    query: str,
    peer_agents: list[dict[str, Any]],
) -> str:
    return STOCK_INBOUND_EXTRACTION_PROMPT_TEMPLATE.format(
        schema=json.dumps(
            STOCK_INBOUND_EXTRACTION_SCHEMA, ensure_ascii=False, indent=2
        ),
        peer_agents=json.dumps(peer_agents, ensure_ascii=False, indent=2),
        query=query,
    )
