from __future__ import annotations

import os
from pathlib import Path

import click
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import dotenv_values, load_dotenv

from .agent_executor import PartsMultiAgentExecutor
from .config import DEFAULT_SKILL_ID, load_config
from .logging_config import configure_logging


def load_agent_dotenv() -> None:
    original_env = dict(os.environ)
    load_dotenv()

    agent_name = os.getenv('AGENT_NAME')
    if not agent_name:
        return

    agent_env_path = Path(f'.env.{agent_name.lower()}')
    if not agent_env_path.exists():
        return

    for key, value in dotenv_values(agent_env_path).items():
        if value is None or key in original_env:
            continue
        os.environ[key] = value


load_agent_dotenv()


@click.command()
def main() -> None:
    config = load_config()
    configure_logging(config.agent_name, config.agent_log_colors)
    skill = AgentSkill(
        id=DEFAULT_SKILL_ID,
        name='Google Sheet 재고 조회',
        description='이 에이전트에 설정된 Google Sheet로 재고 질문에 답합니다.',
        tags=['google-sheets', 'inventory', 'parts', 'stock'],
        examples=[
            '특정 부품 재고 조회해줘',
            '재고가 부족한 품목 알려줘',
            '다른 지점에 이 부품 재고 있는지 확인해줘',
        ],
    )
    agent_card = AgentCard(
        name=config.agent_name,
        description=config.agent_description,
        url=config.app_url,
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )
    request_handler = DefaultRequestHandler(
        agent_executor=PartsMultiAgentExecutor(config),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    uvicorn.run(server.build(), host=config.host, port=config.port)


if __name__ == '__main__':
    main()
