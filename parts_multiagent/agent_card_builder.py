from __future__ import annotations

import json
from pathlib import Path

from a2a.types import AgentCard, AgentCapabilities

from .command_registry import SKILLS


def build_agent_card(config) -> AgentCard:
    """Skill registry에서 자동으로 AgentCard 생성"""

    # SKILLS dict에서 AgentSkill 리스트 생성
    skills = [skill.metadata.to_agent_skill() for skill in SKILLS.values()]

    agent_card = AgentCard(
        name=config.agent_name,
        description=config.agent_description,
        url=config.app_url,
        version="1.0.0",
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=True),
        skills=skills,
    )

    return agent_card


def save_agent_card_json(agent_card: AgentCard, output_path: str) -> None:
    """Agent Card를 JSON으로 저장"""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(agent_card.model_dump(), f, indent=2, ensure_ascii=False)
