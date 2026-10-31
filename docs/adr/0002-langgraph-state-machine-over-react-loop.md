# 0002. An explicit LangGraph state machine over a ReAct loop

Date: 2026-10-31 · Status: Accepted

## Context

The agent answers one question per request: classify it, plan which Gold tables it needs, generate SQL, run guardrails, execute, self-correct at most twice, retrieve documents, and answer with citations ([docs/PLAN.md](../PLAN.md), "Agent design"). Two ways to build that on the LangChain stack the requirement names:

1. **A prebuilt agent loop.** LangChain's `create_agent` (the successor to `create_react_agent`) is a model calling tools in a loop until it decides it is done. The model picks the order of steps and when to stop.
2. **An explicit graph.** LangGraph's `StateGraph` is a typed state object, nodes that read and update it, and edges that decide what runs next, with conditional edges for branching and `START`/`END` sentinels. The code picks the order; the model fills in the judgment inside a node.

The constraints: evals must be able to score each step (tool routing, guardrail compliance, SQL accuracy) and not only the final answer; the guardrails must run before any SQL executes, every time; retries must be bounded; and every run must produce a readable trace.

## Decision

The agent is an explicit LangGraph `StateGraph`. Nodes are plain Python functions with unit tests. The LLM is called inside specific nodes (classify, generate SQL, write the answer) and never decides whether the guardrail node runs. The prebuilt agent loop is not used for the main flow.

## Consequences

**Easier**

- **Deterministic control flow.** The guardrail node always sits between "generate SQL" and "execute". The retry edge is a conditional edge with a counter in the state, so "at most twice" is code, not a prompt instruction. LangGraph's `recursion_limit` is a second backstop: when a graph exceeds its super-step budget it raises `GraphRecursionError` instead of looping.
- **Evals per node.** Tool routing accuracy is the classify node's output compared to the golden route. Guardrail compliance is the guardrail node's verdict. Neither needs the whole run to be re-executed or an LLM judge to be read.
- **Traces that match the design.** Langfuse spans map one-to-one to nodes, so a trace reads like the flow diagram in the plan.
- **Durable execution when it is needed.** LangGraph checkpointers save state at every super-step, keyed by thread, which is what human-in-the-loop interrupts and resume-after-failure build on. The MVP does not need it, but the stretch items (an MCP server, online evals) can switch it on without a redesign.

**Harder**

- More code than a one-line `create_agent`. Each node, edge, and state field is written and tested by hand.
- Less flexibility for questions the flow did not anticipate. A ReAct loop can improvise a third tool call; this graph refuses or fails plainly. For a governed analytics agent that is the intended behavior, but it means new question types need a graph change, not a prompt change.
- Two APIs to know. `create_agent` and its middleware hooks remain the right tool for an open-ended assistant, and the team has to be clear about when to use which.

**At client scale**

The graph is the governance artifact: a client's security review reads the nodes and edges, not a prompt. Scaling adds nodes (a semantic-layer lookup, a policy check, a human approval interrupt backed by a checkpointer) rather than changing the pattern, and multi-step questions become subgraphs. The thing that would change is persistence: a production deployment turns on a durable checkpointer so a run can pause for approval and resume.

## References

`docs.langchain.com` is not in the session's allowed network list, so these pages were confirmed through search results that quote them, not fetched directly. Package versions are from PyPI, which the session can reach.

- LangGraph overview (orchestration runtime for durable execution, streaming, human-in-the-loop, persistence): https://docs.langchain.com/oss/python/langgraph/overview
- Graph API: `StateGraph`, nodes, edges, conditional edges, `START` and `END`: https://docs.langchain.com/oss/python/langgraph/graph-api
- Persistence and checkpointers (state saved at each super-step, grouped into threads): https://docs.langchain.com/oss/python/langgraph/persistence
- `GRAPH_RECURSION_LIMIT` and `GraphRecursionError`: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT
- LangChain agents: `create_agent` as a model calling tools in a loop, with middleware hooks: https://docs.langchain.com/oss/python/langchain/agents and https://docs.langchain.com/oss/python/langchain/middleware/overview
- `create_agent` succeeds `create_react_agent` in LangChain v1: https://docs.langchain.com/oss/python/releases/langchain-v1
- `langgraph` 1.2.19 on PyPI at the time of writing: https://pypi.org/project/langgraph/
