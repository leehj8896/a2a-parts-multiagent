from __future__ import annotations

from dataclasses import dataclass, field
from a2a.types import AgentSkill
from parts_multiagent.constants.skill_prefixes import (
    SKILL_LOCAL_STOCK_INBOUND,
)


@dataclass(frozen=True)
class LocalStockInboundSkillMetadata:
    skill_id: str = SKILL_LOCAL_STOCK_INBOUND
    name: str = "공급처 후보 조회하여 주문하기"
    description: str = "사용자 앱의 주문 품목 기준으로 공급 가능한 peer 후보와 확인 메시지를 반환합니다."
    tags: list[str] = field(default_factory=lambda: ["stock", "inbound", "local"])
    examples: list[str] = field(default_factory=lambda: ["FLT-101 3개 주문", "IC-2020 5개, R-100k 50 주문"])
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
