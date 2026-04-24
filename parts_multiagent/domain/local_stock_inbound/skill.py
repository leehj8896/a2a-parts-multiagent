from __future__ import annotations

from dataclasses import dataclass, field
from a2a.types import AgentSkill
from parts_multiagent.constants.skill_prefixes import (
    SKILL_LOCAL_STOCK_INBOUND,
)


@dataclass(frozen=True)
class LocalStockInboundSkillMetadata:
    skill_id: str = SKILL_LOCAL_STOCK_INBOUND
    name: str = "피어 출고 요청하여 주문하기"
    description: str = "사용자 앱이 로컬 에이전트에 피어 출고를 요청하여 부품을 주문합니다."
    tags: list[str] = field(default_factory=lambda: ["stock", "inbound", "local"])
    examples: list[str] = field(default_factory=lambda: ["부품명 10개", "IC-2020 5개, R-100k 50"])
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


SKILL_METADATA = LocalStockInboundSkillMetadata()
