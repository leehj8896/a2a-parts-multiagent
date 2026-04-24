from __future__ import annotations

from dataclasses import dataclass, field
from a2a.types import AgentSkill
from parts_multiagent.constants.skill_prefixes import (
    SKILL_LOCAL_STOCK_OUTBOUND,
)


@dataclass(frozen=True)
class LocalStockOutboundSkillMetadata:
    skill_id: str = SKILL_LOCAL_STOCK_OUTBOUND
    name: str = "로컬 재고 출고"
    description: str = "로컬 재고에서 부품을 출고합니다."
    tags: list[str] = field(default_factory=lambda: ["stock", "outbound", "local"])
    examples: list[str] = field(default_factory=lambda: ["부품명 5개", "IC-2020 1개"])
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


SKILL_METADATA = LocalStockOutboundSkillMetadata()
