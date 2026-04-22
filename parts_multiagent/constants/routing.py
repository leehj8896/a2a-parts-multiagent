from __future__ import annotations

import json

from typing import Any


ROUTE_PROMPT_TEMPLATE = """
You route a user's inventory question for an A2A LAN Google Sheets multi-agent system.

Return only JSON with this exact schema:
{{
  "route": "local|remote",
  "target_agent_name": "string|null",
  "skill_id": "{skill_id}",
  "task": "string",
  "reason": "string"
}}

Rules:
- Use "local" if the question can be answered by the local agent or no peer clearly matches.
- Use "remote" only when the user asks about another warehouse/device/agent, or a peer agent description/name clearly matches.
- target_agent_name must exactly match one of the peer agent names when route is "remote".
- task must be a self-contained request for the selected agent.

Local agent:
{local_agent}

Peer agents:
{peer_agents}

User question:
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
