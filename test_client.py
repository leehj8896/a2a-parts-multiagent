from __future__ import annotations

import asyncio
import json

from typing import Any
from uuid import uuid4

import click
import httpx

from a2a.client import A2AClient, A2ACardResolver
from a2a.types import (
    DataPart,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    SendMessageSuccessResponse,
    Task,
)
from parts_multiagent.constants.structured_payload_keys import PATH, PAYLOAD


# 구조화 요청(DataPart)으로 A2A SendMessageRequest를 구성합니다.
def create_request(text: str) -> SendMessageRequest:
    message_id = uuid4().hex
    envelope = json.loads(text)
    if not isinstance(envelope, dict):
        raise ValueError('구조화 요청은 JSON object여야 합니다.')
    path = envelope.get(PATH)
    payload = envelope.get(PAYLOAD)
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f'`{PATH}`는 비어있지 않은 문자열이어야 합니다.')
    if not isinstance(payload, dict):
        raise ValueError(f'`{PAYLOAD}`는 JSON object여야 합니다.')

    normalized = {PATH: path.strip(), PAYLOAD: payload}
    parts = [Part(root=DataPart(data=normalized))]

    params = MessageSendParams(
        message=Message(
            role=Role.user,
            parts=parts,
            message_id=message_id,
        ),
        configuration=MessageSendConfiguration(accepted_output_modes=['application/json']),
    )
    return SendMessageRequest(
        id=message_id,
        params=params,
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
        request = create_request(text)
        response = await a2a_client.send_message(request)

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
    try:
        print(asyncio.run(send(base_url, text)))
    except Exception as exc:
        raise click.BadParameter(str(exc)) from exc


if __name__ == '__main__':
    main()
