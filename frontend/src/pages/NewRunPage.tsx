import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { runsApi } from "../lib/api";
import type { PolicyName, PolicyProfile, ResearchBudget } from "../lib/types";

const SMOKE_BUDGET: ResearchBudget = {
  max_tokens: 50_000,
  max_searches: 2,
  max_page_fetches: 4,
  max_elapsed_seconds: 600,
  max_cost_usd: null,
};

const STANDARD_BUDGET: ResearchBudget = {
  max_tokens: 50_000,
  max_searches: 8,
  max_page_fetches: 20,
  max_elapsed_seconds: 600,
  max_cost_usd: null,
};

export function NewRunPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState("");
  const [policy, setPolicy] = useState<PolicyName>("adaptive");
  const [profile, setProfile] = useState<PolicyProfile>("smoke");
  const [budget, setBudget] = useState<ResearchBudget>(SMOKE_BUDGET);

  const createMutation = useMutation({
    mutationFn: runsApi.create,
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${run.run_id}`);
    },
  });

  function selectProfile(nextProfile: PolicyProfile) {
    setProfile(nextProfile);
    setBudget(nextProfile === "smoke" ? SMOKE_BUDGET : STANDARD_BUDGET);
  }

  function updateBudget(field: keyof ResearchBudget, value: number) {
    setBudget((current) => ({ ...current, [field]: value }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (trimmedQuestion.length < 3) return;
    createMutation.mutate({
      question: trimmedQuestion,
      policy,
      profile,
      budget,
    });
  }

  return (
    <div className="page new-run-page">
      <header className="page-header hero-header">
        <div>
          <span className="eyebrow">NEW RESEARCH RUN</span>
          <h1>把研究过程变成<br />可观察的决策。</h1>
        </div>
        <p>
          输入一个技术问题，Agent 会在明确预算内规划、检索、验证证据并生成可追溯报告。
        </p>
      </header>

      <form className="research-form" onSubmit={submit}>
        <section className="form-section question-section">
          <div className="section-number">01</div>
          <div className="form-section-body">
            <label htmlFor="question">研究问题</label>
            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="例如：Python 的 list 和 tuple 有什么主要区别？"
              rows={5}
              minLength={3}
              required
              autoFocus
            />
            <div className="field-hint">
              <span>技术比较、架构选型或概念调研效果最佳</span>
              <span>{question.length} 字</span>
            </div>
          </div>
        </section>

        <section className="form-section">
          <div className="section-number">02</div>
          <div className="form-section-body">
            <span className="field-label">研究策略</span>
            <div className="option-grid two-columns">
              <label className={`choice-card${policy === "adaptive" ? " selected" : ""}`}>
                <input
                  type="radio"
                  name="policy"
                  value="adaptive"
                  checked={policy === "adaptive"}
                  onChange={() => setPolicy("adaptive")}
                />
                <span className="choice-kicker">RECOMMENDED</span>
                <strong>Adaptive Budget</strong>
                <small>根据证据质量和剩余预算动态决定下一步。</small>
              </label>
              <label className={`choice-card${policy === "fixed" ? " selected" : ""}`}>
                <input
                  type="radio"
                  name="policy"
                  value="fixed"
                  checked={policy === "fixed"}
                  onChange={() => setPolicy("fixed")}
                />
                <span className="choice-kicker">BASELINE</span>
                <strong>Fixed Depth</strong>
                <small>按固定深度执行，用作可复现的实验基线。</small>
              </label>
            </div>
          </div>
        </section>

        <section className="form-section">
          <div className="section-number">03</div>
          <div className="form-section-body">
            <span className="field-label">运行规模</span>
            <div className="segmented-control" aria-label="运行规模">
              <button
                type="button"
                className={profile === "smoke" ? "active" : ""}
                onClick={() => selectProfile("smoke")}
              >
                Smoke · 低成本验证
              </button>
              <button
                type="button"
                className={profile === "standard" ? "active" : ""}
                onClick={() => selectProfile("standard")}
              >
                Standard · 完整研究
              </button>
            </div>

            <div className="budget-grid">
              <BudgetInput
                label="Token 上限"
                value={budget.max_tokens}
                onChange={(value) => updateBudget("max_tokens", value)}
              />
              <BudgetInput
                label="搜索次数"
                value={budget.max_searches}
                onChange={(value) => updateBudget("max_searches", value)}
              />
              <BudgetInput
                label="页面抓取"
                value={budget.max_page_fetches}
                onChange={(value) => updateBudget("max_page_fetches", value)}
              />
              <BudgetInput
                label="最长秒数"
                value={budget.max_elapsed_seconds}
                onChange={(value) => updateBudget("max_elapsed_seconds", value)}
              />
            </div>
          </div>
        </section>

        <div className="form-submit-row">
          <div>
            <strong>{profile === "smoke" ? "Smoke 模式" : "Standard 模式"}</strong>
            <span>
              {profile === "smoke"
                ? "1 个子问题，适合验证完整链路"
                : "4 个子问题，适合正式技术调研"}
            </span>
          </div>
          <button
            className="primary-button"
            type="submit"
            disabled={createMutation.isPending || question.trim().length < 3}
          >
            {createMutation.isPending ? "正在创建…" : "开始研究 →"}
          </button>
        </div>
        {createMutation.isError && (
          <div className="form-error" role="alert">
            创建失败：{createMutation.error.message}
          </div>
        )}
      </form>
    </div>
  );
}

function BudgetInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="budget-input">
      <span>{label}</span>
      <input
        type="number"
        min="1"
        value={value}
        onChange={(event) => onChange(Math.max(1, Number(event.target.value)))}
      />
    </label>
  );
}
