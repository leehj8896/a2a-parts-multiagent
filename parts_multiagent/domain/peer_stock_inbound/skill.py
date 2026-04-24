from __future__ import annotations

from dataclasses import dataclass, field
from a2a.types import AgentSkill
from parts_multiagent.constants.skill_prefixes import (
    SKILL_PEER_STOCK_INBOUND,
)


@dataclass(frozen=True)
class PeerStockInboundSkillMetadata:
    skill_id: str = SKILL_PEER_STOCK_INBOUND
    name: str = "피어 재고 입고"
    description: str = "다른 피어 에이전트에 재고 입고를 요청합니다."
    tags: list[str] = field(default_factory=lambda: ["stock", "inbound", "peer"])
    examples: list[str] = field(default_factory=lambda: ['{"agent_name": "B", "raw_items": "부품 10개"}'])
    input_modes: list[str] = field(default_factory=lambda: ["application/json"])
    output_modes: list[str] = field(default_factory=lambda: ["application/json"])

    def to_agent_skill(self) -> AgentSkill:
        return AgentSkill(
            id=self.skill_id,
            name=self.name,
            description=self.description,
            tags=self.tags,
            examples=self.examples,
            input_modes=self.input_modes,
            output_modes=self.output_modes,
        )


SKILL_METADATA = PeerStockInboundSkillMetadata()
