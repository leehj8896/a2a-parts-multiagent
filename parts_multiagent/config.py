from __future__ import annotations

import os

from dataclasses import dataclass
from urllib.parse import urlparse


DEFAULT_LLM_BASE_URL = 'http://joonyy-synology:26414/v1'
DEFAULT_LLM_MODEL = 'github_copilot/gpt-4.1'
DEFAULT_SKILL_ID = 'query_inventory_google_sheet'
DEFAULT_GOOGLE_SHEET_WORKSHEET = 'inventory'
DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 10001


@dataclass(frozen=True)
class GoogleSheetSettings:
    service_account_file: str
    spreadsheet_id: str
    worksheet: str


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
            worksheet=os.getenv(
                'GOOGLE_SHEET_WORKSHEET',
                DEFAULT_GOOGLE_SHEET_WORKSHEET,
            ),
        ),
        llm_base_url=os.getenv('LLM_BASE_URL', DEFAULT_LLM_BASE_URL),
        llm_model=os.getenv('LLM_MODEL', DEFAULT_LLM_MODEL),
        peer_agent_urls=peer_urls,
        host=DEFAULT_HOST,
        port=port,
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
