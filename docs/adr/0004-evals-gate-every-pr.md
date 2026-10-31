# 0004. Evals gate every PR

Date: 2026-10-31 · Status: Accepted

## Context

The plan makes evals the headline, not one layer among four: a public scoreboard shows the scores over time and the PRs the gate blocked ([docs/PLAN.md](../PLAN.md), "Evaluation and observability"). The question this record answers is where evals run and what happens when they fail. The alternatives were a nightly report that someone reads, an eval step that posts a comment but does not block, or a required check that fails the PR.

Constraints: LLM-judge metrics are noisy and cost money on every run; deterministic checks are cheap and exact; a PR that runs 40 questions through Gemini on every push would eat the $25 budget; and a gate that is red for flaky reasons gets ignored within a week.

## Decision

Evals are a required CI status check on every PR, in the same workflow as lint, unit tests, and `dbt build`. The PR runs a fast subset of about 15 golden questions; merge to main and a nightly job run the full set against dev BigQuery and write results to the `eval_runs` table that the scoreboard reads. The gate fails on deterministic metrics (SQL execution accuracy, tool routing, guardrail compliance, retrieval hit rate). LLM-judge metrics (faithfulness, answer correctness where code cannot check it) are reported on every PR and gated with an averaged score and a margin, so one judge disagreement does not block a merge. Every bug found becomes a new golden question.

## Consequences

**Easier**

- **A regression cannot merge quietly.** GitHub's required status checks block merging until the check passes, and the blocked PRs are the evidence the scoreboard shows. Branch protection or a ruleset on `main` names the eval job; job names must be unique across workflows or GitHub reports an ambiguous check.
- **Evals look like tests.** DeepEval metrics each take a `threshold` (default 0.5) and `assert_test` raises when a score falls below it, so an eval is a pytest test and `deepeval test run` or plain `pytest` runs it in CI. No separate eval server to operate.
- **Scoring in code where code can score.** Comparing the agent's result set to the reference query's result set, checking the chosen tools against the expected route, and asserting a guardrail refusal are all exact. They are also free, which is what makes running them on every PR affordable.
- **The golden set grows with the bugs.** `evals/golden.yaml` is versioned next to the code, so a fix and its regression test land in one PR.

**Harder**

- **Gates need a baseline first.** The thresholds in the plan (SQL accuracy ≥ 85%, routing ≥ 90%, guardrails 100%, retrieval ≥ 80%, faithfulness ≥ 0.8) are starting guesses. The gate switches on only after the first baseline run in M3, and tightens from there, never before.
- **Judge metrics cost and drift.** Faithfulness needs an LLM call per question. The PR subset keeps that to about 15 calls, and the judge model and prompt version are logged on every run so a score change can be traced to the judge rather than the agent.
- **Two sets of numbers.** The PR subset runs SQL against DuckDB ([ADR 0003](0003-duckdb-for-local-and-ci-dbt-target.md)); the nightly run uses BigQuery. Only the nightly numbers go on the scoreboard.
- **No built-in "answer correctness" metric.** The source transcript named a DeepEval metric that does not exist as a class. DeepEval's RAG metrics are `FaithfulnessMetric`, `AnswerRelevancyMetric`, `ContextualRelevancyMetric`, `ContextualPrecisionMetric`, and `ContextualRecallMetric`; answer correctness against an expected output is written as a custom `GEval` metric, or, in this project, as a code check for expected facts first.

**At client scale**

The mechanism is the same; the set is different. A client's golden set comes from real tickets and real analysts' SQL rather than planted facts, it is split by business domain so a team owns its own questions, and the nightly run samples production traces (the plan's online-evals stretch goal) so the score reflects the questions people ask, not only the ones the team wrote. The gate also gets a second threshold: no metric may drop by more than a set margin from the last main build, which catches a slow slide that an absolute floor misses.

## References

Fetched and checked in this session:

- Required status checks and rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches and https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets (confirmed through search results that quote them; `docs.github.com` is not in the session's allowed network list)
- Unique job names for required checks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks (same caveat)
- DeepEval metrics, thresholds, and `assert_test` (same caveat for `deepeval.com`): https://deepeval.com/docs/metrics-introduction · https://deepeval.com/docs/metrics-faithfulness · https://deepeval.com/docs/evaluation-unit-testing-in-ci-cd
- DeepEval RAG metrics and custom `GEval` for answer correctness: https://deepeval.com/guides/guides-rag-evaluation · https://deepeval.com/blog/top-5-geval-use-cases
- `deepeval` 4.3.2 and `langfuse` 5.1.0 on PyPI at the time of writing: https://pypi.org/project/deepeval/ · https://pypi.org/project/langfuse/
