# 0005. Gemini through the Vertex AI API, not the Gemini Developer API

Date: 2026-10-31 · Status: Accepted

## Context

Gemini can be called two ways: the Gemini Developer API (`generativelanguage.googleapis.com`, keyed from Google AI Studio) or the Gemini API on Google Cloud (`aiplatform.googleapis.com`). Issue #3 (M0.2) made the call in favor of Google Cloud, and this record writes it down. Constraints: credentials must be IAM, never a key in code or an env file; spend must land on the same project budget as BigQuery and Cloud Run; the region must match BigQuery's; and the model must be swappable from config so evals can compare models.

One naming change matters here. On April 22, 2026, Google renamed Vertex AI to **Gemini Enterprise Agent Platform**; the Vertex AI API became the Agent Platform API, and the Vertex AI documentation is no longer updated. The endpoint, `aiplatform.googleapis.com`, did not change, and the SDK flag is still `vertexai=True`. This repo keeps saying "Vertex AI" for the API and service name, because that is what the hostname, the IAM permission prefix, and the SDK say, and reads "Gemini Enterprise Agent Platform" in Google's docs as the same thing.

## Decision

The agent calls Gemini through `aiplatform.googleapis.com` with the Google Gen AI SDK in Vertex mode, authenticated as a service account through IAM, on the `us-central1` regional endpoint. Embeddings come from the same API. No AI Studio key exists anywhere in the project. The model ID lives in config; the starting default is `gemini-3.8-flash`, and the embedding model is `gemini-embedding-001`.

## Consequences

**Easier**

- **No API key to protect.** Authentication is a Google Cloud service account, so the agent on Cloud Run and the eval job in CI use IAM roles, and Workload Identity Federation (issue #5) covers GitHub Actions. The Gemini Developer API authenticates with an API key, which would be one more secret to rotate and one more way to leak.
- **One bill, one budget.** Gemini usage is billed to `packaging-ops-agent-dev`, so the $25 budget and its alerts cover model spend with everything else.
- **Same geography as the data.** BigQuery datasets are in the `US` multi-region and the model endpoint is `us-central1`. Google's docs note that endpoints alone do not guarantee data residency; the regional choice here is about latency and keeping the design explainable, with the data residency controls available if a client needs them.
- **Enterprise terms.** The Google Cloud side offers data residency, customer-managed encryption keys, SLAs, and support. The Developer API's free tier may use prompts and responses to improve Google products, which rules it out even for a demo that handles only synthetic data, because the project should show the production pattern.
- **Portable code.** The Google Gen AI SDK gives one interface to both APIs. With a few exceptions, code written against one runs against the other, so the choice is a config switch, not a rewrite.

**Harder**

- **Model lifecycle is real.** `gemini-2.5-flash`, the model issue #3 verified, reached its retirement date of October 20, 2026, eleven days before this record. Google's lifecycle page names `gemini-3.8-flash` or `gemini-3.5-flash-lite` as its replacements; this session confirmed `gemini-3.8-flash` and `gemini-3.5-flash` are GA on the `us-central1` endpoint. Models retire roughly a year after release, so the model ID has to be config, every trace has to log it, and a golden-set run is the migration test.
- **Documentation moved.** The old `cloud.google.com/vertex-ai/...` URLs redirect to `docs.cloud.google.com/gemini-enterprise-agent-platform/...`. Links in this repo use the new host.
- **No free tier.** Every eval run costs money. The PR subset and the nightly full run ([ADR 0004](0004-evals-gate-every-pr.md)) are sized with that in mind.

**At client scale**

The same decision, with the controls turned on: a dedicated project per environment, VPC Service Controls around the endpoint, customer-managed encryption keys, and Provisioned Throughput once traffic is steady enough that pay-as-you-go quota is the bottleneck. The model stays a config value, and a client's eval set becomes the acceptance test for every model upgrade Google's retirement calendar forces.

## References

Fetched and checked in this session (`docs.cloud.google.com` is in the allowed network list):

- Differences between the Gemini Developer API and the Google Cloud API (endpoints, authentication, free-tier data use, data residency, SLAs): https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate/migrate-google-ai
- Vertex AI renamed Gemini Enterprise Agent Platform, with the before-and-after names: https://docs.cloud.google.com/gemini-enterprise-agent-platform/vertex-ai-name-changes and the April 22, 2026 entry at https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes
- Google Gen AI SDK: one interface to both APIs, `vertexai=True` / `GOOGLE_GENAI_USE_VERTEXAI`: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/sdks/overview
- Regional and global endpoints, and the note that endpoints do not guarantee data residency: https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations
- Model lifecycle and retirement dates, including `gemini-2.5-flash` (retired October 20, 2026) and its recommended replacements: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions
- Gemini 3.8 Flash (GA, released September 2, 2026): https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash
- Gemini 2.5 Flash retirement notice: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-flash
- Text embeddings, `gemini-embedding-001` with 3072 dimensions and `output_dimensionality`: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/embeddings/get-text-embeddings
- Verified against the live endpoint in this session: `GET https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/google/models/{model}` returned `launchStage: GA` for `gemini-3.8-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-embedding-001`, and `gemini-embedding-2`, and `PUBLIC_PREVIEW` for `gemini-3-flash-preview` and `gemini-3-pro-preview`.
- `google-genai` 2.34.0 and `langchain-google-vertexai` 3.2.5 on PyPI at the time of writing: https://pypi.org/project/google-genai/ · https://pypi.org/project/langchain-google-vertexai/
