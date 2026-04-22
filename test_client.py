from __future__ import annotations

import asyncio

from typing import Any
from uuid import uuid4

import click
import httpx

from a2a.client import A2AClient, A2ACardResolver
from a2a.types import (
    MessageSendParams,
    SendMessageRequest,
    SendMessageSuccessResponse,
    Task,
)


def create_request(text: str) -> SendMessageRequest:
    message_id = uuid4().hex
    payload = {
        'message': {
            'role': 'user',
            'parts': [{'type': 'text', 'text': text}],
            'messageId': message_id,
        },
        'configuration': {'acceptedOutputModes': ['text']},
    }
    return SendMessageRequest(
        id=message_id, params=MessageSendParams.model_validate(payload)
    )


def parts_text(parts: list[Any]) -> list[str]:
    texts = []
    for part in parts or []:
        if getattr(part, 'type', None) == 'text':
            texts.append(part.text)
            continue
        root = getattr(part, 'root', None)
        if root is not None and getattr(root, 'text', None):
            texts.append(root.text)
    return texts


def task_text(task: Task) -> str:
    texts = []
    for artifact in task.artifacts or []:
        texts.extend(parts_text(artifact.parts))
    if not texts and task.status and task.status.message:
        texts.extend(parts_text(task.status.message.parts))
    return '\n'.join(texts) if texts else task.model_dump_json(indent=2)


async def send(base_url: str, text: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        card = await A2ACardResolver(client, base_url).get_agent_card()
        a2a_client = A2AClient(client, card, url=base_url)
        response = await a2a_client.send_message(create_request(text))

    if not isinstance(response.root, SendMessageSuccessResponse):
        return response.model_dump_json(indent=2)
    result = response.root.result
    if isinstance(result, Task):
        return task_text(result)
    return '\n'.join(parts_text(getattr(result, 'parts', [])))


@click.command()
@click.option('--url', 'base_url', default='http://localhost:10001')
@click.argument('text')
def main(base_url: str, text: str) -> None:
    print(asyncio.run(send(base_url, text)))


if __name__ == '__main__':
    main()
