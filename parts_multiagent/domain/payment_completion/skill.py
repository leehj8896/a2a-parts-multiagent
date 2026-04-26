from __future__ import annotations

from dataclasses import dataclass, field

from a2a.types import AgentSkill

from parts_multiagent.constants.skill_prefixes import SKILL_PAYMENT_COMPLETION


@dataclass(frozen=True)
class PaymentCompletionSkillMetadata:
    skill_id: str = SKILL_PAYMENT_COMPLETION
    name: str = "주문 결제 완료 처리"
    description: str = (
        "결제 완료된 주문의 상태를 '결제대기'에서 '성공'으로 업데이트합니다."
    )
    tags: list[str] = field(
        default_factory=lambda: ["payment", "completion", "order"]
    )
    examples: list[str] = field(
        default_factory=lambda: [
            '{"order_id":"a1b2c3d4e5"}'
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


SKILL_METADATA = PaymentCompletionSkillMetadata()
