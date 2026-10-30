"""FastAPI entry point.

M0 ships an empty app: a health check and nothing else. The agent, the
``/ask`` endpoint, and the ``/evals`` scoreboard arrive in later milestones.
"""

from fastapi import FastAPI

app = FastAPI(
    title="packaging-ops-agent",
    description="Agentic analytics over a synthetic packaging supply chain.",
    version="0.0.1",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe used by Cloud Run and by CI."""
    return {"status": "ok"}
