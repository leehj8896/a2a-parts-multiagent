from __future__ import annotations

import logging

from io import StringIO

import pandas as pd


MAX_CELL_WIDTH = 40


def log_inventory_response(
    *,
    logger: logging.Logger,
    local_agent: str,
    source_agent: str,
    query: str,
    response: str,
) -> None:
    rendered_tables = _render_csv_tables(response)
    if rendered_tables:
        logger.info(
            '\n%s\nlocal_agent=%s\nsource_agent=%s\nquery=%s\n'
            'response_type=table\n\n%s\n%s',
            '=' * 72,
            local_agent,
            source_agent,
            query,
            '\n\n'.join(rendered_tables),
            '=' * 72,
        )
        return

    logger.info(
        '\n%s\nlocal_agent=%s\nsource_agent=%s\nquery=%s\n'
        'response_type=text\n\n%s\n%s',
        '=' * 72,
        local_agent,
        source_agent,
        query,
        response.strip() or '(empty response)',
        '=' * 72,
    )


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
