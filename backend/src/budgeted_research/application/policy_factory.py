from __future__ import annotations

from typing import Literal

from budgeted_research.policies.adaptive_budget import (
    AdaptiveBudgetConfig,
    AdaptiveBudgetPolicy,
)
from budgeted_research.policies.base import ResearchPolicy
from budgeted_research.policies.fixed_depth import FixedDepthConfig, FixedDepthPolicy

PolicyProfile = Literal["standard", "smoke"]


def normalize_policy_name(policy: str) -> str:
    aliases = {
        "fixed": "fixed_depth",
        "fixed_depth": "fixed_depth",
        "adaptive": "adaptive_budget",
        "adaptive_budget": "adaptive_budget",
    }
    try:
        return aliases[policy.strip().lower()]
    except KeyError as error:
        raise ValueError(f"unknown research policy: {policy}") from error


def build_research_policy(
    policy: str,
    profile: PolicyProfile = "standard",
) -> ResearchPolicy:
    if profile not in {"standard", "smoke"}:
        raise ValueError(f"unknown research profile: {profile}")
    normalized = normalize_policy_name(policy)
    if normalized == "fixed_depth":
        return FixedDepthPolicy(
            FixedDepthConfig(
                subquestion_count=1,
                search_results_per_query=2,
                pages_per_subquestion=1,
                selected_chunks_per_subquestion=2,
                max_evidence_per_subquestion=2,
            )
            if profile == "smoke"
            else None
        )
    return AdaptiveBudgetPolicy(
        AdaptiveBudgetConfig(
            subquestion_count=1,
            search_results_per_query=2,
            max_sources_per_subquestion=2,
            max_search_rounds_per_subquestion=2,
            max_extraction_rounds_per_subquestion=2,
            selected_chunks_per_extraction=2,
            max_evidence_per_extraction=2,
        )
        if profile == "smoke"
        else None
    )
