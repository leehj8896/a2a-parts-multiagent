from __future__ import annotations

import logging

from io import StringIO
from typing import Any

import pandas as pd

from parts_multiagent.constants.skill_prefixes import (
    SKILL_INVENTORY_LOOKUP_LOCAL,
)
from parts_multiagent.utils.constants.structured_payload_keys import AGENT_NAME

MAX_CELL_WIDTH = 40
INVENTORY_LOG_SKILLS = {
    SKILL_INVENTORY_LOOKUP_LOCAL,
}
DEFAULT_RESPONSE_STATUS = 'unknown'
STATUS_ATTRIBUTE = 'status'
MESSAGE_ATTRIBUTE = 'message'
ERROR_MESSAGE_ATTRIBUTE = 'error_message'


def log_structured_skill_success(
    *,
    logger: logging.Logger,
    agent_name: str,
    skill_id: str,
    request: object,
    response: object,
) -> None:
    # 구조화 skill 실행 성공을 공통 병목에서 요약 로그로 기록합니다.
    status = _response_status(response)
    message = _response_message(response)
    logger.info(
        'skill 실행 완료: agent=%s skill_id=%s status=%s request=%s',
        agent_name,
        skill_id,
        status,
        _summarize_value(request),
        extra={AGENT_NAME: agent_name},
    )
    if skill_id in INVENTORY_LOG_SKILLS:
        log_inventory_response(
            logger=logger,
            local_agent=agent_name,
            source_agent=agent_name,
            query=_request_query(request),
            response=message,
        )


def log_structured_skill_not_found(
    *,
    logger: logging.Logger,
    agent_name: str,
    path: str,
    skill_id: str,
) -> None:
    # 지원하지 않는 구조화 skill 요청을 경고 로그로 기록합니다.
    logger.warning(
        '지원하지 않는 skill 요청: agent=%s path=%s skill_id=%s',
        agent_name,
        path,
        skill_id,
        extra={AGENT_NAME: agent_name},
    )


def log_structured_request_parse_failure(
    *,
    logger: logging.Logger,
    agent_name: str,
    skill_id: str,
    payload: dict[str, object],
    error: Exception,
) -> None:
    # 구조화 요청 payload 파싱 실패를 경고 로그로 기록합니다.
    logger.warning(
        '구조화 요청 해석 실패: agent=%s skill_id=%s payload=%s error=%s: %s',
        agent_name,
        skill_id,
        _summarize_value(payload),
        type(error).__name__,
        error,
        extra={AGENT_NAME: agent_name},
    )


def log_structured_skill_exception(
    *,
    logger: logging.Logger,
    agent_name: str,
    skill_id: str,
    request: object,
    error: Exception,
) -> None:
    # 구조화 skill handler 예외를 stack trace와 함께 기록합니다.
    logger.exception(
        'skill 실행 예외: agent=%s skill_id=%s request=%s error=%s: %s',
        agent_name,
        skill_id,
        _summarize_value(request),
        type(error).__name__,
        error,
        extra={AGENT_NAME: agent_name},
    )


def log_inventory_response(
    *,
    logger: logging.Logger,
    local_agent: str,
    source_agent: str,
    query: str,
    response: str,
) -> None:
    # 재고 응답을 로그로 기록하면서 CSV 표 형태는 보기 좋게 렌더링합니다.
    rendered_tables = _render_csv_tables(response)
    if rendered_tables:
        logger.info(
            '\n%s\n로컬_에이전트=%s\n응답_에이전트=%s\n질의=%s\n'
            '응답_형식=표\n\n%s\n%s',
            '=' * 72,
            local_agent,
            source_agent,
            query,
            '\n\n'.join(rendered_tables),
            '=' * 72,
            extra={AGENT_NAME: source_agent},
        )
        return

    logger.info(
        '\n%s\n로컬_에이전트=%s\n응답_에이전트=%s\n질의=%s\n'
        '응답_형식=텍스트\n\n%s\n%s',
        '=' * 72,
        local_agent,
        source_agent,
        query,
        response.strip() or '(빈 응답)',
        '=' * 72,
        extra={AGENT_NAME: source_agent},
    )


def log_peer_agent_response(
    *,
    logger: logging.Logger,
    local_agent: str,
    source_agent: str,
    request_text: str,
    response: str,
) -> None:
    # 피어 응답을 source agent 색상으로 상세 로그에 기록합니다.
    rendered_tables = _render_csv_tables(response)
    if rendered_tables:
        logger.info(
            '\n%s\n로컬_에이전트=%s\n응답_에이전트=%s\n요청=%s\n'
            '응답_형식=표\n\n%s\n%s',
            '=' * 72,
            local_agent,
            source_agent,
            request_text,
            '\n\n'.join(rendered_tables),
            '=' * 72,
            extra={AGENT_NAME: source_agent},
        )
        return

    logger.info(
        '\n%s\n로컬_에이전트=%s\n응답_에이전트=%s\n요청=%s\n'
        '응답_형식=텍스트\n\n%s\n%s',
        '=' * 72,
        local_agent,
        source_agent,
        request_text,
        response.strip() or '(빈 응답)',
        '=' * 72,
        extra={AGENT_NAME: source_agent},
    )


def _response_status(response: object) -> str:
    value = getattr(response, STATUS_ATTRIBUTE, DEFAULT_RESPONSE_STATUS)
    if isinstance(value, str) and value:
        return value
    return DEFAULT_RESPONSE_STATUS


def _response_message(response: object) -> str:
    message = getattr(response, MESSAGE_ATTRIBUTE, '')
    if isinstance(message, str) and message:
        return message
    error_message = getattr(response, ERROR_MESSAGE_ATTRIBUTE, '')
    if isinstance(error_message, str) and error_message:
        return error_message
    return str(response)


def _request_query(request: object) -> str:
    query = getattr(request, 'query', '')
    if isinstance(query, str) and query:
        return query
    return _summarize_value(request)


def _summarize_value(value: Any) -> str:
    text = repr(value)
    if len(text) <= MAX_CELL_WIDTH * 3:
        return text
    return text[: MAX_CELL_WIDTH * 3 - 3] + '...'


def _render_csv_tables(response: str) -> list[str]:
    tables = []
    for section in response.split('\n\n'):
        lines = [line for line in section.splitlines() if line.strip()]
        if not lines:
            continue

        csv_start = _find_csv_start(lines)
        if csv_start is None:
            continue

        title = '\n'.join(lines[:csv_start]).strip()
        csv_text = '\n'.join(lines[csv_start:])
        try:
            frame = pd.read_csv(StringIO(csv_text))
        except Exception:
            continue
        if frame.empty or len(frame.columns) <= 1:
            continue

        rendered = _format_table(frame)
        tables.append(f'{title}\n{rendered}' if title else rendered)
    return tables


def _find_csv_start(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if ',' not in line:
            continue
        try:
            frame = pd.read_csv(StringIO('\n'.join(lines[index:])), nrows=1)
        except Exception:
            continue
        if len(frame.columns) > 1:
            return index
    return None


def _format_table(frame: pd.DataFrame) -> str:
    rows = [
        [_trim_cell(value) for value in frame.columns],
        *[
            [_trim_cell(value) for value in row]
            for row in frame.astype(str).itertuples(index=False, name=None)
        ],
    ]
    widths = [
        max(len(row[column_index]) for row in rows)
        for column_index in range(len(rows[0]))
    ]
    separator = '+-' + '-+-'.join('-' * width for width in widths) + '-+'
    rendered = [separator, _format_row(rows[0], widths), separator]
    rendered.extend(_format_row(row, widths) for row in rows[1:])
    rendered.append(separator)
    return '\n'.join(rendered)


def _format_row(row: list[str], widths: list[int]) -> str:
    cells = [
        value.ljust(width)
        for value, width in zip(row, widths, strict=True)
    ]
    return '| ' + ' | '.join(cells) + ' |'


def _trim_cell(value: object) -> str:
    text = str(value)
    if len(text) <= MAX_CELL_WIDTH:
        return text
    return text[: MAX_CELL_WIDTH - 3] + '...'
