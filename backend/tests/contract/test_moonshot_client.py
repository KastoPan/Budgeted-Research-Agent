import json

import httpx
import pytest
from openai import AsyncOpenAI

from budgeted_research.providers.llm.moonshot import (
    MoonshotChatClient,
    MoonshotPlanner,
    _temperature_for_mode,
)


@pytest.mark.asyncio
async def test_moonshot_client_parses_json_and_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["response_format"] == {"type": "json_object"}
        assert body["temperature"] == 0.6
        assert body["max_tokens"] == 256
        assert body["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": '{"answer":"ok"}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    openai_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://api.moonshot.test/v1",
        http_client=http_client,
    )
    client = MoonshotChatClient(
        api_key="test-key",
        model="test-model",
        client=openai_client,
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
    )

    try:
        payload, usage = await client.generate_json(
            "system", "user", max_completion_tokens=256
        )
    finally:
        await openai_client.close()

    assert payload == {"answer": "ok"}
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.cost_usd == pytest.approx(0.00014)


def test_moonshot_client_selects_temperature_for_thinking_mode() -> None:
    assert _temperature_for_mode(None, thinking_enabled=False) == 0.6
    assert _temperature_for_mode(None, thinking_enabled=True) == 1.0
    assert _temperature_for_mode(0.8, thinking_enabled=False) == 0.8


@pytest.mark.asyncio
async def test_moonshot_client_repairs_invalid_json_once_and_combines_usage() -> None:
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        content = "not valid JSON" if call_count == 1 else '{"answer":"repaired"}'
        prompt_tokens = 10 if call_count == 1 else 20
        completion_tokens = 5 if call_count == 1 else 10
        return httpx.Response(
            200,
            json={
                "id": f"chatcmpl-{call_count}",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    openai_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://api.moonshot.test/v1",
        http_client=http_client,
    )
    client = MoonshotChatClient(
        api_key="test-key",
        model="test-model",
        client=openai_client,
    )

    try:
        payload, usage = await client.generate_json("system", "user")
    finally:
        await openai_client.close()

    assert call_count == 2
    assert payload == {"answer": "repaired"}
    assert usage.input_tokens == 30
    assert usage.output_tokens == 15


@pytest.mark.asyncio
async def test_moonshot_planner_retries_schema_failure_and_combines_usage() -> None:
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        content = (
            '{"subquestions":[{"id":"sq_01"}]}'
            if call_count == 1
            else (
                '{"subquestions":[{"id":"sq_01","question":"Main trade-off",'
                '"search_query":"main trade-off","rationale":"Compare evidence"}]}'
            )
        )
        return httpx.Response(
            200,
            json={
                "id": f"chatcmpl-{call_count}",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    openai_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://api.moonshot.test/v1",
        http_client=http_client,
    )
    planner = MoonshotPlanner(
        MoonshotChatClient(
            api_key="test-key",
            model="test-model",
            client=openai_client,
        )
    )

    try:
        subquestions, usage = await planner.plan("Compare approaches", count=1)
    finally:
        await openai_client.close()

    assert call_count == 2
    assert [item.id for item in subquestions] == ["sq_01"]
    assert usage.input_tokens == 20
    assert usage.output_tokens == 10
