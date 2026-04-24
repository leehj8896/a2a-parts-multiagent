from __future__ import annotations

import click
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from .agent_executor import PartsMultiAgentExecutor
from .agent_card_builder import build_agent_card, save_agent_card_json
from .config import load_agent_dotenv, load_config
from .logging_config import configure_logging


@click.command()
def main() -> None:
    load_agent_dotenv()
    config = load_config()
    configure_logging(config.agent_name, config.agent_log_colors)

    # ✅ Agent Card 자동 생성 (Skill registry에서)
    agent_card = build_agent_card(config)
    save_agent_card_json(agent_card, 'parts_multiagent/generated/agent_card.json')

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
