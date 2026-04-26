from __future__ import annotations

import os
from pathlib import Path

from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import dotenv_values, load_dotenv


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


DEFAULT_LLM_BASE_URL = 'http://joonyy-synology:26414/v1'
DEFAULT_LLM_MODEL = 'github_copilot/gpt-4.1'
DEFAULT_SKILL_ID = 'query_inventory_google_sheet'
DEFAULT_GOOGLE_SHEET_INVENTORY_WORKSHEET = 'inventory'
DEFAULT_GOOGLE_SHEET_ORDER_WORKSHEET = 'orders'
DEFAULT_INVENTORY_HEADERS = ('부품번호', '부품명', '수량', '가격(원)')
DEFAULT_ORDER_HEADERS = (
    '기록시각',
    '주문번호',
    '에이전트',
    '구분',
    '부품번호',
    '수량',
    '변경전재고',
    '변경후재고',
    '가격',
    '요청내용',
    '상태',
)
DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 10001
SUPPORTED_LOG_COLORS = {
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'white',
    'bright_red',
    'bright_green',
    'bright_yellow',
    'bright_blue',
    'bright_magenta',
    'bright_cyan',
    'bright_white',
}


@dataclass(frozen=True)
class GoogleSheetSettings:
    service_account_file: str
    spreadsheet_id: str
    inventory_worksheet: str
    order_worksheet: str
    inventory_headers: tuple[str, ...]
    order_headers: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_ORDER_HEADERS
    )


@dataclass(frozen=True)
class PartsAgentConfig:
    agent_name: str
    agent_description: str
    app_url: str
    google_sheet: GoogleSheetSettings
    llm_base_url: str
    llm_model: str
    peer_agent_urls: list[str]
    host: str
    port: int
    agent_log_colors: dict[str, str]
    supplier_delivery_time_by_agent: dict[str, int]


# 런타임 환경변수를 읽어 에이전트 설정 객체를 구성합니다.
def load_config() -> PartsAgentConfig:
    agent_name = os.getenv('AGENT_NAME')
    if not agent_name:
        raise ValueError(
            'AGENT_NAME environment variable is required. '
            'Set it when running this agent, for example: '
            'AGENT_NAME=A uv run python -m parts_multiagent'
        )

    port = _load_port()
    peer_urls = [
        url.strip()
        for url in os.getenv('PEER_AGENT_URLS', '').split(',')
        if url.strip()
    ]
    app_url = _load_app_url(peer_urls, port)
    peer_urls = _exclude_self_url(peer_urls, app_url)
    return PartsAgentConfig(
        agent_name=agent_name,
        agent_description=os.getenv(
            'AGENT_DESCRIPTION',
            'Queries parts inventory from Google Sheets.',
        ),
        app_url=app_url,
        google_sheet=GoogleSheetSettings(
            service_account_file=_required_env(
                'GOOGLE_SERVICE_ACCOUNT_FILE'
            ),
            spreadsheet_id=_required_env('GOOGLE_SHEET_ID'),
            inventory_worksheet=os.getenv(
                'GOOGLE_INVENTORY_WORKSHEET',
                DEFAULT_GOOGLE_SHEET_INVENTORY_WORKSHEET,
            ),
            order_worksheet=os.getenv(
                'GOOGLE_ORDER_WORKSHEET',
                DEFAULT_GOOGLE_SHEET_ORDER_WORKSHEET,
            ),
            inventory_headers=tuple(
                os.getenv(
                    'GOOGLE_SHEET_INVENTORY_HEADERS',
                    ','.join(DEFAULT_INVENTORY_HEADERS),
                ).split(',')
            ),
            order_headers=tuple(
                os.getenv(
                    'GOOGLE_SHEET_ORDER_HEADERS',
                    ','.join(DEFAULT_ORDER_HEADERS),
                ).split(',')
            ),
        ),
        llm_base_url=os.getenv('LLM_BASE_URL', DEFAULT_LLM_BASE_URL),
        llm_model=os.getenv('LLM_MODEL', DEFAULT_LLM_MODEL),
        peer_agent_urls=peer_urls,
        host=DEFAULT_HOST,
        port=port,
        agent_log_colors=_load_agent_log_colors(),
        supplier_delivery_time_by_agent=(
            _load_supplier_delivery_time_by_agent()
        ),
    )


def _required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise ValueError(f'{name} environment variable is required.')
    return value


def _load_port() -> int:
    raw_port = os.getenv('PORT', str(DEFAULT_PORT))
    try:
        return int(raw_port)
    except ValueError as exc:
        raise ValueError(
            f'PORT environment variable must be an integer, got: {raw_port!r}'
        ) from exc


def _load_agent_log_colors() -> dict[str, str]:
    colors = {}
    for item in os.getenv('LOG_COLORS', '').split(','):
        name, separator, color = item.strip().partition('=')
        if not separator:
            name, separator, color = item.strip().partition(':')
        name = name.strip()
        color = color.strip().lower()
        if name and color in SUPPORTED_LOG_COLORS:
            colors[name] = color
    return colors


# 공급처별 배송 예정시간을 시간 단위 정수 매핑으로 읽고 검증합니다.
def _load_supplier_delivery_time_by_agent() -> dict[str, int]:
    delivery_time_by_agent: dict[str, int] = {}
    for item in os.getenv(
        'SUPPLIER_DELIVERY_TIME_BY_AGENT',
        '',
    ).split(','):
        supplier_agent, separator, estimated_delivery_time = item.strip().partition('=')
        supplier_agent = supplier_agent.strip()
        estimated_delivery_time = estimated_delivery_time.strip()
        if not separator or not supplier_agent or not estimated_delivery_time:
            continue
        delivery_time_by_agent[supplier_agent] = _parse_delivery_time_hours(
            supplier_agent=supplier_agent,
            raw_delivery_time=estimated_delivery_time,
        )
    return delivery_time_by_agent


# 배송 예정시간 문자열을 0보다 큰 시간 단위 정수로 변환합니다.
def _parse_delivery_time_hours(
    *,
    supplier_agent: str,
    raw_delivery_time: str,
) -> int:
    try:
        delivery_time_hours = int(raw_delivery_time)
    except ValueError as exc:
        raise ValueError(
            'SUPPLIER_DELIVERY_TIME_BY_AGENT values must be integers that '
            f'represent hours, got {raw_delivery_time!r} for {supplier_agent!r}.'
        ) from exc

    if delivery_time_hours <= 0:
        raise ValueError(
            'SUPPLIER_DELIVERY_TIME_BY_AGENT values must be greater than 0, '
            f'got {delivery_time_hours!r} for {supplier_agent!r}.'
        )
    return delivery_time_hours


def _load_app_url(peer_urls: list[str], port: int) -> str:
    base_url = os.getenv('BASE_URL')
    if base_url:
        return f'{base_url.strip().rstrip("/")}:{port}'
    return _infer_app_url(peer_urls, DEFAULT_HOST, port)


def _exclude_self_url(peer_urls: list[str], app_url: str) -> list[str]:
    normalized_app_url = _normalize_url(app_url)
    return [
        url
        for url in peer_urls
        if _normalize_url(url) != normalized_app_url
    ]


def _normalize_url(url: str) -> str:
    return url.strip().rstrip('/')


def _infer_app_url(peer_urls: list[str], host: str, port: int) -> str:
    matching_urls = []
    for url in peer_urls:
        parsed = urlparse(url)
        if parsed.port == port:
            matching_urls.append(url)
    if len(matching_urls) == 1:
        return matching_urls[0]
    return f'http://{host}:{port}'
