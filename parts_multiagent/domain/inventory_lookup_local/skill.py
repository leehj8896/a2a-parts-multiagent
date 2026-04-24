from __future__ import annotations

from dataclasses import dataclass, field
from a2a.types import AgentSkill
from parts_multiagent.constants.skill_prefixes import (
    SKILL_INVENTORY_LOOKUP_LOCAL,
)


@dataclass(frozen=True)
class InventoryLookupLocalSkillMetadata:
    skill_id: str = SKILL_INVENTORY_LOOKUP_LOCAL
    name: str = "로컬 재고 조회"
    description: str = "이 에이전트의 로컬 재고를 조회합니다."
    tags: list[str] = field(default_factory=lambda: ["inventory", "local"])
    examples: list[str] = field(default_factory=lambda: ["부품 IC-2020", "STARTMTR01"])
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


SKILL_METADATA = InventoryLookupLocalSkillMetadata()
