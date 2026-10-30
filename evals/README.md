# evals/

The eval suite: `golden.yaml` (about 40 questions with category, expected tool route, reference SQL or expected sources, and expected facts), the runner, and the metrics (code checks first, DeepEval LLM judge only for what code cannot check).

Filled in **M3 · Evals + tracing**. A fast subset runs on every PR and the full set runs nightly, writing to the BigQuery `eval_runs` table that the public scoreboard reads.
