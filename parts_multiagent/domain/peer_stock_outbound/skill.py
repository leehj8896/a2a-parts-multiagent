from __future__ import annotations

from dataclasses import dataclass, field
from a2a.types import AgentSkill
from parts_multiagent.constants.skill_prefixes import (
    SKILL_PEER_STOCK_OUTBOUND,
)


@dataclass(frozen=True)
class PeerStockOutboundSkillMetadata:
    skill_id: str = SKILL_PEER_STOCK_OUTBOUND
    name: str = "다른 에이전트에 출고요청 및 주문하기"
    description: str = "로컬 에이전트가 다른 피어 에이전트에 재고 출고를 요청하고 부품을 주문합니다."
    tags: list[str] = field(default_factory=lambda: ["stock", "outbound", "peer"])
    examples: list[str] = field(default_factory=lambda: ['{"agent_name": "B", "raw_items": "부품 5개"}', "B 판매점에 STARTMTR01 1개 주문"])
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


SKILL_METADATA = PeerStockOutboundSkillMetadata()
