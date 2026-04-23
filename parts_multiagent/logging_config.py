from __future__ import annotations

import logging


ANSI_COLORS = {
    'red': '31',
    'green': '32',
    'yellow': '33',
    'blue': '34',
    'magenta': '35',
    'cyan': '36',
    'white': '37',
    'bright_red': '91',
    'bright_green': '92',
    'bright_yellow': '93',
    'bright_blue': '94',
    'bright_magenta': '95',
    'bright_cyan': '96',
    'bright_white': '97',
}
RESET = '\033[0m'


class AgentPrefixFormatter(logging.Formatter):
    def __init__(
        self,
        default_agent_name: str,
        agent_log_colors: dict[str, str],
    ) -> None:
        super().__init__('%(levelname)s:%(name)s:%(agent_prefix)s %(message)s')
        self.default_agent_name = default_agent_name
        self.agent_log_colors = agent_log_colors

    def format(self, record: logging.LogRecord) -> str:
        agent_name = getattr(record, 'agent_name', self.default_agent_name)
        color = self.agent_log_colors.get(agent_name)
        record.agent_prefix = f'[{agent_name}]'
        formatted = super().format(record)
        return _color_text(formatted, color)


def configure_logging(
    agent_name: str,
    agent_log_colors: dict[str, str],
) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(AgentPrefixFormatter(agent_name, agent_log_colors))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def _color_text(text: str, log_color: str | None) -> str:
    color_code = ANSI_COLORS.get(log_color or '')
    if not color_code:
        return text
    return f'\033[{color_code}m{text}{RESET}'
