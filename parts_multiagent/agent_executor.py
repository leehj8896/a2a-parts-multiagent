from __future__ import annotations

import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message
from a2a.utils.parts import get_data_parts
from a2a.utils.artifact import new_text_artifact
from a2a.utils.task import new_task

from .agent import PartsMultiAgent
from .constants.structured_payload_keys import PATH, PAYLOAD
from .config import PartsAgentConfig
from .utils.response_serialization import response_to_json_dict


class PartsMultiAgentExecutor(AgentExecutor):
    def __init__(self, config: PartsAgentConfig) -> None:
        self.agent = PartsMultiAgent(config)

    # 구조화 요청 응답을 JSON 문자열로 직렬화해 A2A artifact로 반환합니다.
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                final=False,
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        '재고 요청을 라우팅하는 중입니다...'
                    ),
                ),
            )
        )

        result = ''
        message = context.message
        if message is not None:
            for data in get_data_parts(message.parts):
                path = data.get(PATH)
                payload = data.get(PAYLOAD)
                if isinstance(path, str) and isinstance(payload, dict):
                    response = await self.agent.invoke_structured_response(
                        path,
                        payload,
                    )
                    result = json.dumps(
                        response_to_json_dict(response),
                        ensure_ascii=False,
                    )
                    break

        if not result:
            result = 'DataPart(application/json) 형식만 지원합니다.'

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                append=False,
                last_chunk=True,
                artifact=new_text_artifact(name='result', text=result),
            )
        )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                final=True,
                status=TaskStatus(state=TaskState.completed),
            )
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception('취소를 지원하지 않습니다')
