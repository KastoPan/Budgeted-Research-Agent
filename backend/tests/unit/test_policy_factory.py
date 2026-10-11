from budgeted_research.application.policy_factory import build_research_policy
from budgeted_research.policies.adaptive_budget import AdaptiveBudgetPolicy
from budgeted_research.policies.fixed_depth import FixedDepthPolicy


def test_smoke_profile_builds_minimal_adaptive_policy() -> None:
    policy = build_research_policy("adaptive", "smoke")

    assert isinstance(policy, AdaptiveBudgetPolicy)
    assert policy.config.subquestion_count == 1
    assert policy.config.search_results_per_query == 2
    assert policy.config.max_sources_per_subquestion == 2
    assert policy.config.selected_chunks_per_extraction == 2


def test_smoke_profile_builds_minimal_fixed_policy() -> None:
    policy = build_research_policy("fixed", "smoke")

    assert isinstance(policy, FixedDepthPolicy)
    assert policy.config.subquestion_count == 1
    assert policy.config.search_results_per_query == 2
    assert policy.config.pages_per_subquestion == 1
    assert policy.config.selected_chunks_per_subquestion == 2


def test_standard_profile_keeps_policy_defaults() -> None:
    adaptive = build_research_policy("adaptive", "standard")
    fixed = build_research_policy("fixed", "standard")

    assert isinstance(adaptive, AdaptiveBudgetPolicy)
    assert adaptive.config.subquestion_count == 4
    assert isinstance(fixed, FixedDepthPolicy)
    assert fixed.config.subquestion_count == 4
