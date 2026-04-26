from __future__ import annotations

from dataclasses import dataclass, field

from a2a.types import AgentSkill

from parts_multiagent.constants.skill_prefixes import (
    SKILL_ORDER_SELECTION,
)


@dataclass(frozen=True)
class OrderSelectionSkillMetadata:
    skill_id: str = SKILL_ORDER_SELECTION
    name: str = "주문 후보 선택 후 결제 진행"
    description: str = (
        "사용자가 선택한 공급처와 품목으로 피어 출고를 요청하고 결제 URL을 반환합니다."
    )
    tags: list[str] = field(
        default_factory=lambda: ["order", "selection", "payment"]
    )
    examples: list[str] = field(
        default_factory=lambda: [
            '{"supplier_agent":"B","items":[{"part":"FLT-101","quantity":3}]}'
        ]
    )
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


SKILL_METADATA = OrderSelectionSkillMetadata()
