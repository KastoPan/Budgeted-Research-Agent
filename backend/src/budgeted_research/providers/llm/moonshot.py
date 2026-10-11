from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from budgeted_research.domain.errors import InvalidProviderOutputError
from budgeted_research.domain.models import (
    DocumentChunk,
    EvidenceItem,
    ReportAssertion,
    ReportSection,
    ResearchReport,
    SubQuestion,
    Usage,
)


class MoonshotChatClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.moonshot.cn/v1",
        timeout_seconds: float = 20.0,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
        max_completion_tokens: int = 4_096,
        default_temperature: float | None = None,
        thinking_enabled: bool = False,
        max_retries: int = 0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self._input_cost_per_million = input_cost_per_million
        self._output_cost_per_million = output_cost_per_million
        self._max_completion_tokens = max_completion_tokens
        self._thinking_enabled = thinking_enabled
        self._default_temperature = _temperature_for_mode(
            default_temperature, thinking_enabled
        )
        self._owns_client = client is None
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> tuple[dict[str, Any], Usage]:
        effective_temperature = (
            self._default_temperature if temperature is None else temperature
        )
        content, usage = await self._complete(
            system_prompt,
            user_prompt,
            effective_temperature,
            max_completion_tokens,
        )
        try:
            return _parse_json_object(content), usage
        except json.JSONDecodeError:
            repaired_content, repair_usage = await self._complete(
                (
                    "Repair the supplied text into one valid JSON object. Preserve its "
                    "meaning and fields. Output JSON only, without Markdown fences."
                ),
                content,
                effective_temperature,
                max_completion_tokens,
            )
            combined_usage = _add_usage(usage, repair_usage)
            try:
                return _parse_json_object(repaired_content), combined_usage
            except json.JSONDecodeError as error:
                raise InvalidProviderOutputError(
                    "Moonshot returned invalid JSON after one format-repair attempt",
                    usage=combined_usage,
                ) from error

    async def _complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_completion_tokens: int | None,
    ) -> tuple[str, Usage]:
        completion = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_completion_tokens or self._max_completion_tokens,
            extra_body={
                "thinking": {
                    "type": "enabled" if self._thinking_enabled else "disabled"
                }
            },
        )
        content = completion.choices[0].message.content
        if not content:
            usage = _usage_from_completion(
                completion,
                self._input_cost_per_million,
                self._output_cost_per_million,
            )
            finish_reason = completion.choices[0].finish_reason or "unknown"
            reasoning_present = bool(
                getattr(completion.choices[0].message, "reasoning_content", None)
                or (completion.choices[0].message.model_extra or {}).get(
                    "reasoning_content"
                )
            )
            raise InvalidProviderOutputError(
                "Moonshot returned an empty response "
                f"(finish_reason={finish_reason}, "
                f"reasoning_content_present={str(reasoning_present).lower()})",
                usage=usage,
            )
        usage = _usage_from_completion(
            completion,
            self._input_cost_per_million,
            self._output_cost_per_million,
        )
        return content, usage

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()


def _temperature_for_mode(
    configured_temperature: float | None, thinking_enabled: bool
) -> float:
    if configured_temperature is not None:
        return configured_temperature
    return 1.0 if thinking_enabled else 0.6


def _usage_from_completion(
    completion: Any,
    input_cost_per_million: float,
    output_cost_per_million: float,
) -> Usage:
    prompt_tokens = completion.usage.prompt_tokens if completion.usage else 0
    completion_tokens = completion.usage.completion_tokens if completion.usage else 0
    cost = (
        prompt_tokens * input_cost_per_million
        + completion_tokens * output_cost_per_million
    ) / 1_000_000
    return Usage(
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        cost_usd=cost,
    )


def _add_usage(left: Usage, right: Usage) -> Usage:
    return Usage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cost_usd=left.cost_usd + right.cost_usd,
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(payload, dict):
            return payload
        raise json.JSONDecodeError("JSON top level must be an object", stripped, 0)

    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise json.JSONDecodeError("no valid JSON object found", stripped, 0)


class _PlannerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subquestions: list[SubQuestion]


class MoonshotPlanner:
    def __init__(
        self, client: MoonshotChatClient, max_schema_retries: int = 1
    ) -> None:
        if max_schema_retries < 0:
            raise ValueError("max_schema_retries must be non-negative")
        self._client = client
        self._max_schema_retries = max_schema_retries

    async def plan(self, question: str, count: int) -> tuple[list[SubQuestion], Usage]:
        expected_ids = [f"sq_{index:02d}" for index in range(1, count + 1)]
        system_prompt = (
            "你是技术调研规划器。只输出合法 JSON，不执行搜索。将问题拆成互补、"
            "不重复且可独立检索的子问题。JSON 顶层字段必须是 subquestions。"
        )
        user_prompt = (
            f"主问题：{question}\n"
            f"必须正好生成 {count} 个子问题。每项字段只能是 id、question、"
            "search_query、rationale；id 依次使用 "
            f"{', '.join(expected_ids)}。"
        )
        combined_usage = Usage()
        last_error: Exception | None = None
        for attempt in range(self._max_schema_retries + 1):
            try:
                payload, usage = await self._client.generate_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_completion_tokens=2_048,
                )
            except Exception as error:
                if combined_usage.total_tokens > 0:
                    raise InvalidProviderOutputError(
                        "planner schema retry failed after a billable response",
                        usage=combined_usage,
                    ) from error
                raise
            combined_usage = _add_usage(combined_usage, usage)
            try:
                parsed = _PlannerPayload.model_validate(payload)
                actual_ids = [item.id for item in parsed.subquestions]
                if actual_ids != expected_ids:
                    raise ValueError(
                        f"expected IDs {expected_ids}, received {actual_ids}"
                    )
            except (ValidationError, ValueError) as error:
                last_error = error
                if attempt < self._max_schema_retries:
                    user_prompt += (
                        "\n上一次输出未通过结构校验。请重新生成完整对象，严格遵守字段、"
                        "数量和 ID，不要添加任何其他字段。"
                    )
                    continue
                break
            return parsed.subquestions, combined_usage
        raise InvalidProviderOutputError(
            "invalid planner JSON schema after retry",
            usage=combined_usage,
        ) from last_error


class _EvidenceDraft(BaseModel):
    # Extra explanatory fields do not weaken the evidence contract, so tolerate them.
    # The three fields below remain mandatory and are the only ones admitted downstream.
    model_config = ConfigDict(extra="ignore")
    claim: str
    support_span: str
    source_id: str


class _EvidencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: list[_EvidenceDraft] = Field(default_factory=list)


class MoonshotEvidenceExtractor:
    def __init__(self, client: MoonshotChatClient) -> None:
        self._client = client

    async def extract(
        self,
        subquestion: SubQuestion,
        chunks: list[DocumentChunk],
        max_items: int,
    ) -> tuple[list[EvidenceItem], Usage]:
        chunk_payload = [
            {
                "chunk_id": chunk.id,
                "source_id": chunk.source_id,
                "title": chunk.source_title,
                "url": str(chunk.source_url),
                "content": chunk.content,
            }
            for chunk in chunks
        ]
        payload, usage = await self._client.generate_json(
            system_prompt=(
                "你是证据抽取器。只输出合法 JSON。仅抽取资料能够直接支持的原子事实。"
                "support_span 必须逐字来自对应 source 的 content，不得改写。"
                "source_id 必须复制资料中的 source_id，不要填写 chunk_id。"
                "顶层字段必须是 evidence，每项只包含 claim、support_span、source_id。"
                '严格使用结构：{"evidence":[{"claim":"...","support_span":"...",'
                '"source_id":"..."}]}。'
            ),
            user_prompt=(
                f"子问题：{subquestion.question}\n"
                f"最多抽取 {max_items} 条证据。资料：\n"
                + json.dumps(chunk_payload, ensure_ascii=False)
            ),
            max_completion_tokens=2_048,
        )
        try:
            parsed = _EvidencePayload.model_validate(payload)
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in error.errors(include_url=False, include_input=False)
            )
            raise InvalidProviderOutputError(
                f"invalid evidence JSON schema: {details}", usage=usage
            ) from error

        chunks_by_source_id = {chunk.source_id: chunk for chunk in chunks}
        evidence: list[EvidenceItem] = []
        for index, draft in enumerate(parsed.evidence[:max_items], start=1):
            chunk = chunks_by_source_id.get(draft.source_id)
            if chunk is None:
                raise InvalidProviderOutputError(
                    f"evidence references unknown source {draft.source_id}",
                    usage=usage,
                )
            evidence.append(
                EvidenceItem(
                    id=f"ev_{subquestion.id}_{index:02d}",
                    subquestion_id=subquestion.id,
                    claim=draft.claim,
                    support_span=draft.support_span,
                    source_id=chunk.source_id,
                    source_url=chunk.source_url,
                    source_title=chunk.source_title,
                    retrieved_at=chunk.retrieved_at,
                )
            )
        return evidence, usage


class _ReportAssertionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class _ReportSectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subquestion_id: str = Field(min_length=1)
    assertions: list[_ReportAssertionPayload]


class _ReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: list[_ReportSectionPayload]


class MoonshotReportWriter:
    def __init__(self, client: MoonshotChatClient) -> None:
        self._client = client

    async def write(
        self,
        question: str,
        subquestions: list[SubQuestion],
        evidence: list[EvidenceItem],
    ) -> tuple[ResearchReport, Usage]:
        payload, usage = await self._client.generate_json(
            system_prompt=(
                "你是证据编排器，只输出合法 JSON。顶层字段只能是 sections；每个 "
                "section 只能包含 subquestion_id 和 assertions；每个 assertion 只能包含 "
                "text 和 evidence_ids。text 必须逐字复制某一条输入证据的 "
                "claim，不得改写、概括、拼接或补充任何事实。每个 evidence_id 对应的 "
                "claim 都必须与 text 相同，并且属于该 subquestion_id。可以省略不重要的 "
                "证据；每个 section 最多保留 6 条 assertions，并按对回答主问题的重要性 "
                "从高到低排列；证据不足的部分保留空 assertions。不得输出 Markdown 或 URL。"
            ),
            user_prompt=(
                f"主问题：{question}\n"
                "子问题：\n"
                + json.dumps(
                    [item.model_dump(mode="json") for item in subquestions],
                    ensure_ascii=False,
                )
                + "\n证据：\n"
                + json.dumps(
                    [item.model_dump(mode="json") for item in evidence],
                    ensure_ascii=False,
                )
            ),
            max_completion_tokens=4_096,
        )
        try:
            parsed = _ReportPayload.model_validate(payload)
        except ValidationError as error:
            raise InvalidProviderOutputError(
                "invalid report JSON schema", usage=usage
            ) from error
        return ResearchReport(
            sections=[
                ReportSection(
                    subquestion_id=section.subquestion_id,
                    heading=next(
                        (
                            item.question
                            for item in subquestions
                            if item.id == section.subquestion_id
                        ),
                        section.subquestion_id,
                    ),
                    assertions=[
                        ReportAssertion(
                            text=assertion.text,
                            evidence_ids=assertion.evidence_ids,
                        )
                        for assertion in section.assertions
                    ],
                )
                for section in parsed.sections
            ],
        ), usage
