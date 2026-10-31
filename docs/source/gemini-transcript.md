# Gemini transcript: the conversation the plan grew from

Source material for [docs/PLAN.md](../PLAN.md). This is the Gemini conversation Jason had before the plan was written, committed as provenance. The plan kept the core idea (a packaging supply-chain agent over medallion data, with evals gating CI) and changed four things: BigQuery instead of Databricks, one tool per layer, evals as the headline, and no resume numbers until the scoreboard produces them.

Treat technical details below as unverified. The plan notes that some do not check out, such as a DeepEval metric name and a Unity Catalog audit query. Nothing here is a citation.

---

this is a job req for mckinsey quantum black. what would you build to gain exposure to these tools?:


YOUR QUALIFICATIONS AND SKILLS

    U.S. Citizenship is a requirement for this role (you must be able to be staffed on Critical Industries work which includes Government, Defense, Aerospace, Utilities, etc.)
    Degree in Computer Science/Engineering, or equivalent experience
    2+ years of relevant professional experience building and deploying data solutions
    Strong proficiency in Python and SQL for data engineering and experience writing robust, production-grade code, including deploying code across environments
    Proven experience building end-to-end data pipelines and platforms for Agentic AI, Generative AI, Machine Learning, or Business Intelligence, covering data preparation, embeddings generation, vector search, and system integration using modern frameworks (Spark, dbt, LangChain)
    A strong foundation in system design, data storage, and reliability with commonly used data platforms (Databricks, Snowflake, BigQuery, PSQL, etc.) and data engineering tools (e.g., Pandas, Spark, dbt, etc.)
    Hands-on experience with MLOps/LLMOps principles, including CI/CD for data workflows, automated agent evaluation (LangSmith, Opik, Langfuse), and infrastructure as code (Terraform)
    Experience building systems with different data formats (structured vs unstructured) and data processing methods (streaming vs batch) and deploying across major cloud platforms (AWS, Azure, GCP)
    Exceptional time management in a complex and largely autonomous work environment
    Commercial client-facing or senior stakeholder management experience is beneficial
    Experience using coding agents (Cursor, Claude Code, Codex, etc.) is a plus
    Strong communication skills, both verbal and written, in English and local office language(s)
    Willingness to travel as required 

This QuantumBlack (McKinsey's AI & Analytics arm) job description is a showcase for production-grade Data Engineering for Agentic & Generative AI.   
McKinsey & Company

QuantumBlack specifically emphasizes what they call an "Agentic AI Mesh" and "Composable Platform Architecture"—moving away from toy LLM wrappers toward reliable, evaluated, and production-tested enterprise data systems.   
McKinsey

To directly match every bullet in this job description, you should build an End-to-End Enterprise Agentic Data Platform & Eval Framework using your packaging domain knowledge (e.g., corrugator efficiency / mill operations / paper logistics) or a public supply-chain dataset.
What to Build: The "Enterprise Packaging Supply Chain Data Mesh & Agent Engine"

Build a project that treats data pipelines, vector search, and LLM agent orchestration as one unified, evaluated engineering pipeline deployed via Infrastructure-as-Code.

                  ┌────────────────────────────────────────────────────────┐
                  │                 INFRASTRUCTURE & CI/CD                 │
                  │        Terraform  |  GitHub Actions  |  Docker         │
                  └───────────────────────────┬────────────────────────────┘
                                              │
 ┌────────────────────────────────────────────┴────────────────────────────────────────────┐
 │                                   DATA PIPELINE LAYER                                   │
 │  Structured Data (SQL/Parquet)                Unstructured Data (PDFs / Lab Reports)     │
 │  [dbt + PySpark / DuckDB]                     [ChromaDB / pgvector / Qdrant]             │
 └─────────────────────┬───────────────────────────────────────────┬───────────────────────┘
                       │                                           │
                       ▼                                           ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   AGENTIC AI LAYER                                      │
 │                            [LangChain / Semantic Kernel]                                │
 │          Data Agent (SQL / DuckDB)          <--->          Vector Agent (RAG)           │
 └────────────────────────────────────────────┬────────────────────────────────────────────┘
                                              │
                                              ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   LLMOps & EVALUATION                                   │
 │                        [Opik / Langfuse / DeepEval / RAGAS]                             │
 │             Evaluates: SQL Generation Accuracy | Groundedness | Faithfulness           │
 └─────────────────────────────────────────────────────────────────────────────────────────┘

How This System Covers Every Requirement in the Req
1. Data Engineering & Transformation (dbt, PySpark, Databricks/Snowflake/DuckDB)

    Structured Stream/Batch Pipeline: Use dbt and PySpark (or DuckDB) to transform raw JSON/CSV log data (e.g., corrugator speed, waste %, plant downtime, order runs) into medallion layer tables (Bronze -> Silver -> Gold).

    Unstructured Processing & Embeddings: Chunk and embed unstructured PDF data (e.g., equipment maintenance manuals, paper board quality lab specs) using OpenAI or HuggingFace embeddings into a vector store (pgvector, ChromaDB, or Qdrant).

2. Agentic AI & Systems Integration (LangChain, Model Context Protocol)

    Multi-Agent Orchestrator: Build a LangChain or Semantic Kernel process agent that routes user/exec queries between two distinct tools:

        Text-to-SQL Tool: Runs structured analytical queries against your dbt Gold tables.

        Vector Retrieval Tool: Performs hybrid vector search across equipment repair manuals and quality specs.

    Tool Calling & Interoperability: Integrate open protocols like the Model Context Protocol (MCP) to expose your database as an agent tool.

3. LLMOps, Observability & Automated Evals (Langfuse / Opik / DeepEval)

    Tracing & Logging: Pipe agent execution runs into an open-source observability framework like Langfuse or Opik to track token latency, prompt costs, and tool-call chains.

    CI/CD Eval Suite: Create a golden test set of 30+ domain questions. Run automated evaluations on every pull request to score:

        SQL Execution Accuracy: Did the agent join the correct plant dimension tables?

        Faithfulness & Groundedness (RAGAS/DeepEval): Did the agent synthesize actual metric numbers without hallucinating?

4. Infrastructure-as-Code & CI/CD (Terraform, Docker, GitHub Actions)

    Terraform: Write modular Terraform scripts to provision cloud resources (e.g., AWS S3/EC2 or GCP Cloud Run/Cloud Storage, Postgres instance).

    CI/CD Pipeline: GitHub Action workflow that:

        Lints Python code and runs dbt test.

        Spins up Docker containers.

        Triggers the DeepEval agent evaluation suite.

        Deploys updated agent code across environments (Dev/Prod).

5. Coding Agent Provenance (Cursor, Claude Code)

    Document in your repository README how you leveraged Claude Code or Cursor for automated test generation, dbt model generation, and refactoring—directly addressing QuantumBlack's callout for modern developer toolchains.

How to Highlight This on Your Resume / Interview

When interviewing at QuantumBlack, frame this project around their core consulting themes: Governance, Production-grade AI, and Systemic Evaluation.   
McKinsey

    Enterprise Agentic Data Platform & LLMOps Engine

        Designed and built an end-to-end Agentic Data Mesh using dbt, PySpark, LangChain, and pgvector to query structured warehouse metrics and unstructured operational documentation.

        Implemented an automated LLMOps Evaluation Pipeline using Opik/DeepEval integrated into GitHub Actions CI/CD, tracking SQL Accuracy, Faithfulness, and Latency across 50+ benchmark test cases.

        Provisioned cloud infrastructure via Terraform and containerized deployment pipelines using Docker and Cloud Run with scale-to-zero compute economics.

        Utilized Claude Code and Cursor to accelerate dbt model generation, unit test coverage, and agent tool-calling definitions.

eg how to weave databricks and all this stuff into a google cloud project?

Weaving a heavy-duty data platform like Databricks into a Google Cloud architecture—especially while targeting a role like McKinsey's QuantumBlack—is a fantastic way to show you understand enterprise data infrastructure, not just basic API scripts.

When you combine Databricks on Google Cloud with native GCP services, you are essentially building a Hybrid Lakehouse Architecture. Here is how the pieces fit together logically and how you map out a project design for it:
The Architecture: Where Databricks Meets GCP

In an enterprise cloud setup, Google Cloud provides the foundational infrastructure, network security, and native AI/data warehousing hooks, while Databricks acts as the heavy compute, data engineering, and agentic ML engine.

┌────────────────────────────────────────────────────────────────────────┐
│                        GOOGLE CLOUD PLATFORM (GCP)                     │
│                                                                        │
│  [Google Cloud Storage (GCS)] ──(Raw Data/Parquet)                     │
│               │                                                        │
│               ▼                                                        │
│  [Databricks on Google Cloud] (Runs on GKE / Compute Engine)          │
│   ├── dbt / PySpark Pipelines (Medallion Architecture)                 │
│   ├── Unity Catalog (Unified Governance)                               │
│   └── Vector Search & Agent Orchestration (LangChain / Mosaic AI)      │
│               │                                                        │
│               ▼                                                        │
│  [Google BigQuery] ◄──(Lakehouse Federation) ──► [Databricks SQL]       │
└────────────────────────────────────────────────────────────────────────┘

How the Components Interlock:

    Storage Layer (Google Cloud Storage - GCS):

        Raw data lands in GCS buckets (JSON logs, CSV operational feeds, PDFs). This serves as your cloud object storage backbone.

    Compute & Transformation Layer (Databricks on GCP):

        Databricks natively integrates with GCS and Google Kubernetes Engine (GKE). You use PySpark or dbt-databricks inside Databricks notebooks/workflows to process your Bronze -> Silver -> Gold medallion tables.   
        Google

    Governance Layer (Databricks Unity Catalog):

        Manages access control, data lineage, and vector embeddings for your structured and unstructured datasets across the workspace.

    Data Warehousing & Serving (BigQuery + Databricks SQL):

        Instead of choosing just one, you use Lakehouse Federation—allowing Google BigQuery to query tables directly inside Databricks (or vice versa), which is a massive enterprise design pattern.

    AI & Agentic Layer (Vertex AI / Gemini API + LangChain):

        You can leverage Google AI Studio / Vertex AI models inside Databricks notebooks to build your data agents and run evaluations using DeepEval or Opik.

How to Frame This on a Resume / Portfolio

If you want to impress a firm like McKinsey, your architecture narrative shouldn't just be "I used a bunch of tools." It should be framed around solving a complex enterprise data bottleneck.

    Multi-Cloud Data Mesh & Enterprise AI Architecture

        Architected a hybrid data platform leveraging Databricks on Google Cloud integrated with GCS, BigQuery, and Unity Catalog to process multi-format supply chain streams.

        Implemented automated medallion pipelines using PySpark and dbt, reducing batch processing latency and establishing strict data lineage governance.

        Deployed an Agentic AI retrieval layer connecting structured Lakehouse tables with unstructured document embeddings, governed by automated LLMOps evaluation pipelines.

If You Want to Build This Cheaply (or Free):

Running a full Databricks workspace normally requires an enterprise cloud commitment, but you can build a local/cloud hybrid equivalent that mirrors the exact same architectural principles:

    The "Databricks-Lite" Stack: Use DuckDB + dbt-duckdb locally to replicate the exact same Medallion architecture (Bronze/Silver/Gold) and PySpark-style dataframe operations, paired with Google AI Studio for the agent layer.

    In your documentation or interview architecture diagrams, explicitly map how your local DuckDB/dbt setup scales conceptually into a Databricks on GCP + BigQuery enterprise deployment.

yes i want to understand the internals, i want the details/messy shit explained, the logs, etc.

In high-stakes technical environments (and interviews at elite teams like QuantumBlack), generalities are ignored. Winning candidates talk about the exact wires, system tables, telemetry streams, and low-level mechanics of how data moves, fails, and gets governed under the hood.

Below is the deep internal architecture of how Databricks on Google Cloud operates, including telemetry formats, audit payloads, and real execution traces.
1. Control Plane vs. Data Plane (The GCP GCP Plumbing)

Databricks on GCP operates via a split architecture:

    The Control Plane (Managed by Databricks): Houses the UI, web application, cluster manager, and MLflow tracing servers.

    The Data Plane (Inside YOUR GCP Project): All compute infrastructure runs inside your custom Google Cloud VPC. When a cluster spins up, it provisions Google Compute Engine (GCE) instances inside your subnets or deploys pods to Google Kubernetes Engine (GKE).

  DATABRICKS CONTROL PLANE (GCP)
  ┌─────────────────────────────────────────┐
  │ Web UI | Workspace Service | MLflow UI  │
  └────────────────────┬────────────────────┘
                       │ HTTPS / mTLS
                       ▼
  YOUR GCP PROJECT (DATA PLANE / VPC)
  ┌─────────────────────────────────────────┐
  │ Private Subnet: Compute Engine Nodes    │
  │  ├── Driver Node (Spark Driver + OTel)  │
  │  └── Worker Nodes (Executors)           │
  │ Storage: Google Cloud Storage (GCS)     │
  │  └── Delta Lake Logs (_delta_log/*.json)│
  └─────────────────────────────────────────┘

Low-Level Log Storage Mechanics

When Spark writes a batch or Delta table to Google Cloud Storage (GCS), it writes immutable .parquet data files alongside atomic commit logs inside gs://your-bucket/table_name/_delta_log/00000000000000000000.json.

    ACID Guarantees over GCS: Because object stores historically lacked atomic directory renames, Databricks uses a custom GCS Commit Protocol (a distributed lock managed by the control plane or Unity Catalog) to guarantee atomic multi-writer commit logs directly to GCS.

2. The Internal Log Engine & System Tables

Enterprise data engineering requires knowing how to query system telemetry directly. Unity Catalog automatically routes workspace telemetry into System Tables stored inside Delta format.
Audit Logs Payload Structure (system.access.audit)

Every query execution, tool call, or permission grant generates a JSON audit payload in the Unity Catalog system schema.

If an agent attempts to execute an invalid SQL statement against a Delta table, Unity Catalog logs the exact identity, IP, and failure code:   
Databricks
SQL

-- Querying failed agent SQL attempts in Unity Catalog System Tables
SELECT 
    event_time,
    user_identity.email AS caller_identity,
    request_params.statement AS executed_sql,
    response.error_code,
    response.error_message
FROM system.access.audit
WHERE service_name = 'unityCatalog'
  AND action_name = 'generateTemporaryTableCredential'
  AND response.status_code != 200
ORDER BY event_time DESC 
LIMIT 10;

Raw Telemetry Payload (otel_logs)

Databricks applications and agent containers export runtime logs via standard OpenTelemetry (OTel) pipelines into structured Delta target tables (otel_logs, otel_spans, otel_metrics):   
docs.databricks.com
JSON

{
  "time": "2026-10-30T14:22:01.104Z",
  "service_name": "packaging-agent-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "attributes": {
    "event.name": "tool_execution",
    "tool.name": "execute_duckdb_margin_calc",
    "tool.status": "success",
    "execution_time_ms": 142
  },
  "body": "Executed SQL: SELECT plant_id, SUM(margin) FROM gold_yields GROUP BY 1"
}

3. Agent Execution & LLMOps Tracing (MLflow Trace Mechanics)

When building an agent using LangChain or Semantic Kernel on Databricks, you wrap tool calls with MLflow Tracing. This records the exact call-and-response loop, token counts, and tool execution latency into MLflow.
Python

import mlflow
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent

# Enable automated tracing for all agent execution loops
mlflow.langchain.autolog()

with mlflow.start_run(run_name="agent_eval_run_004") as run:
    # Agent receives user prompt
    response = sql_agent.invoke({
        "input": "Calculate the Q3 gross margin impact for corrugator upgrades in Plant B."
    })
    
    # Extract trace metadata logged under the hood
    trace_id = mlflow.get_active_trace().info.request_id
    print(f"Captured MLflow Trace ID: {trace_id}")

What Gets Captured in the Trace Payload

Inside the MLflow UI (or exported programmatically), the trace expands into a waterfall span graph:

[SPAN 1: Agent Execution] - 1,420ms (Prompt Tokens: 412, Completion Tokens: 88)
 ├── [SPAN 2: LLM Router Intent Classification] - 310ms
 │    └── Decision: Select Tool -> "sql_db_query"
 ├── [SPAN 3: Tool Call: sql_db_query] - 850ms
 │    ├── Input: "SELECT SUM(gross_margin) FROM gold_plant_yields WHERE plant = 'Plant B' AND quarter = 'Q3'"
 │    └── Output: [{"plant": "Plant B", "gross_margin": 1420500.00}]
 └── [SPAN 4: Final Synthesis Engine] - 260ms
      └── Response: "The corrugator upgrade at Plant B generated $1.42M in Q3 gross margin..."

4. Continuous Evaluation Script (DeepEval + MLflow Integration)

To show a hiring manager that you enforce rigor, run an automated evaluation script that pulls agent output, compares it against your golden ground-truth dataset, and computes Faithfulness and SQL Execution Correctness scores:
Python

import os
from deepeval import evaluate
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

def run_agent_eval_suite(test_cases_dataset):
    """
    Executes automated evaluation metrics against a golden dataset.
    """
    results = []
    
    # Define LLM-as-a-Judge evaluation metrics
    faithfulness_metric = FaithfulnessMetric(threshold=0.8)
    relevancy_metric = AnswerRelevancyMetric(threshold=0.7)

    for item in test_cases_dataset:
        # Run agent to get output and context
        agent_output = run_agent(item["input_prompt"])
        
        # Construct DeepEval Test Case
        test_case = LLMTestCase(
            input=item["input_prompt"],
            actual_output=agent_output["response"],
            retrieval_context=agent_output["retrieved_sql_results"],
            expected_output=item["ground_truth_answer"]
        )
        
        # Measure metrics
        evaluate([test_case], metrics=[faithfulness_metric, relevancy_metric])
        
        results.append({
            "prompt": item["input_prompt"],
            "faithfulness_score": faithfulness_metric.score,
            "faithfulness_passed": faithfulness_metric.is_successful(),
            "reason": faithfulness_metric.reason
        })
        
    return results

How This Translates to Technical Credibility

When interviewing or showcasing this project:

    You don't talk about "using Databricks" — you talk about configuring Unity Catalog system tables (system.access.audit), monitoring OTel pipelines (otel_logs), and inspecting execution spans in MLflow.   
    Databricks

    You don't talk about "writing an AI chatbot" — you talk about building a deterministic SQL/tool orchestrator governed by DeepEval assertion checks in CI/CD pipelines.

    You don't ignore cloud costs — you highlight how containerized Cloud Run microservices query local DuckDB snapshot layers for testing, and scale seamlessly into Databricks Lakehouse Federation over Google Cloud Storage in production.

yes design me a plan to build something that i can take notes on, the technologies, et.

Here is a comprehensive blueprint for building a local-first, production-grade Agentic Data & Evals Platform. You can build, test, and run this entirely on your machine for $0, using the exact toolchain that high-end teams like McKinsey's QuantumBlack respect.
Project Title: "Lakehouse-Agent-Eval" (The Personal Financial & Supply Chain Intelligence Engine)
The Core Objective

Build an AI Agent system that answers complex natural language queries by querying structured local Delta Lake / DuckDB data (emulating enterprise data warehouses like Databricks or Snowflake), while running an automated evaluation pipeline (DeepEval) to measure SQL accuracy, tool routing correctness, and hallucination rates.   
Medium
The Tech Stack (Zero-Cost / Open-Source)
Layer	Technology	Purpose
Storage & File Format	Delta Lake + Parquet	Open table format for immutable ACID-compliant data storage.
Execution Engine	DuckDB	In-process columnar SQL execution engine (reads Delta files natively via delta_scan()).
Transformation / Modeling	dbt (Data Build Tool) + dbt-duckdb	Manages Bronze → Silver → Gold medallion data transformations.
AI Agent Orchestration	Python (LangChain / Semantic Kernel)	Orchestrates tool-calling, intent routing, and natural language generation.
LLM Inference	Google AI Studio (Gemini Flash API)	Free-tier LLM backbone for agent reasoning and SQL generation.
LLMOps & Tracing	Langfuse (Self-Hosted / Cloud Free)	Captures agent traces, token costs, latency, and tool-call waterfalls.
Evaluation Framework	DeepEval	Programmatic test runner evaluating SQL correctness, faithfulness, and relevancy.
Infrastructure / CI/CD	Docker & GitHub Actions	Containerizes the stack and automates eval test suites on pull requests.
Step-by-Step Implementation Blueprint
Step 1: Initialize the Local Lakehouse Data Pipeline (dbt + DuckDB)

    Create a local project directory structured like an enterprise data warehouse:
    Plaintext

    financial-agent-platform/
    ├── data/                  # Raw CSV/Parquet files (simulated packaging/finance data)
    ├── models/                # dbt SQL models
    │   ├── bronze/            # Ingested raw logs
    │   ├── silver/            # Cleaned domain tables (facilites, orders, returns)
    │   └── gold/              # Aggregated fact/dimension tables (margin analysis)
    ├── agents/                # Python LangChain agent code
    ├── evaluation/            # Golden test datasets & DeepEval scripts
    ├── Dockerfile
    └── dbt_project.yml

    Write dbt models to transform raw operational CSVs (e.g., equipment run-rates, cost allocations, portfolio returns) through a strict medallion architecture.

    Configure dbt-duckdb so that all transformations materialize instantly into local .duckdb and .parquet files.

Step 2: Build the Agentic Tool Layer

Write a Python script using LangChain that exposes your gold-layer DuckDB tables as a secure, read-only SQL tool.

    The System Prompt: Give the agent strict instructions: "You are an enterprise data assistant. You have read-only access to a DuckDB warehouse. Always write ANSI SQL, inspect table schemas first, and never perform destructive updates."

    Structured Output: Ensure the agent returns both the natural language answer and the intermediary telemetry (generated SQL statement, execution time, row counts).

Step 3: Implement the LLMOps Tracing (Langfuse)

    Wrap your agent runtime execution loop with Langfuse decorators or callbacks.

    Every time a user submits a query, Langfuse records a nested trace showing:

        Prompt tokens & completion tokens.

        Router decision span.

        SQL execution time and result payload.

Step 4: Build the Automated Evaluation Suite (DeepEval)

Create an evaluation file (evaluation/test_agent.py) containing a Golden Dataset of 20+ test cases:
Python

from deepeval import evaluate
from deepeval.metrics import FaithfulnessMetric, SQLInjectionMetric
from deepeval.test_case import LLMTestCase

# Example Golden Test Case
test_case = LLMTestCase(
    input="What was the total gross margin for Plant B in Q3?",
    actual_output=agent.run("What was the total gross margin for Plant B in Q3?"),
    retrieval_context=["SELECT plant_id, SUM(margin) FROM gold_margins WHERE plant='Plant B' AND quarter='Q3'"],
    expected_output="The total gross margin for Plant B in Q3 was $1,420,500."
)

evaluate([test_case], metrics=[FaithfulnessMetric(threshold=0.8)])

Step 5: Containerization & CI/CD (Docker + GitHub Actions)

    Write a lightweight Dockerfile that packages your DuckDB file, dbt models, and Python agent code into a single container image.

    Set up a GitHub Actions workflow (.github/workflows/ci.yml) that triggers on every git push:

        Runs dbt test to ensure data warehouse data integrity.

        Executes the DeepEval test script against the agent.

        Fails the build if the agent's hallucination rate or SQL accuracy drops below enterprise threshold (e.g., < 90% pass rate).

Why This Architecture Wins Interviews

    It Proves Rigor: You aren't just calling an OpenAI endpoint; you are managing data contracts through dbt, query execution through DuckDB, and behavioral compliance through DeepEval.

    It Mimics Enterprise Patterns: The exact pipeline you run locally on your laptop maps 1:1 to a massive Databricks Unity Catalog + MLflow + Delta Lake setup in a cloud environment.

    Zero Cost: Runs entirely offline or via free-tier cloud APIs, giving you total freedom to iterate.

can you look at websites?

I can directly search public websites, documentation, and web sources in real time.

However, I cannot log into private user accounts, navigate interactive sessions that require user credentials, or view local web interfaces running on your private machine.

To help you move forward, let's look at how we can implement and trace the project locally.

does that project have an agent rigor or is it primarily a data agent? Make sense? Like should your expertise, for example in my case, most of my experience in sql server? do you lean into that or try to branch out for a project demo? are these things you can put on your resume?

This project balances data engineering core competence with agentic software engineering rigor. It's designed to showcase your core strengths without over-pivoting into a gimmick.
1. Is it a "Data Agent" or "Agent Rigor"?

It is primarily a Process/Workflow Agent with Data Capabilities.

    Why it's not just a Data Agent: A basic data agent is simply a Text-to-SQL bot—you ask a question, an LLM generates a SQL query, executes it against a database, and returns a table. That is a single-step tool call and is considered table-stakes.

    Where the Agent Rigor lives: The rigor comes from the supervisor pattern, orchestration, and evaluation framework.

        Planning & Routing: The agent determines whether it needs structured data (DuckDB/SQL), unstructured knowledge (repair manuals/lab specs in a vector DB), or a deterministic Python tool (margin calculation).

        Fallback & Recovery: If the generated SQL fails a schema check or returns a zero-row edge case, the agent reads the database error, corrects its syntax, and retries.

        LLMOps & Evals: You aren't just trusting that the LLM gives good answers; you run a CI/CD test suite (DeepEval) measuring Faithfulness, SQL Syntax Correctness, and Tool Selection Accuracy on every git commit.

2. Leaning into SQL Server vs. Branching Out

Lean into your core strengths, but frame them using modern cloud-native terminology.

Hiring managers at places like QuantumBlack or enterprise firms want to see deep data fundamentals (modeling, query optimization, schema design, enterprise domains) combined with modern delivery patterns (lakehouse, containerization, CI/CD, agentic tooling).

    Keep your SQL Foundation front and center: Over a decade of SQL Server experience means you deeply understand indexing, execution plans, relational algebra, and analytical window functions. That is your superpower. LLMs write bad SQL when they don't understand the underlying schema constraints; your project proves you know how to structure data so an agent can't mess it up.

    Branch out just enough in the toolchain: Instead of running full SQL Server, swap the execution engine to DuckDB or dbt for the demo. Why?

        DuckDB uses ANSI SQL (so 95% of your T-SQL knowledge translates instantly).

        It shows you understand modern columnar analytics, Lakehouse Parquet storage, and zero-infrastructure local setups.

3. Can You Put This on Your Resume?

Yes—and it should be placed in a dedicated "Projects & Architectures" or "AI Data Engineering Platforms" section.

Instead of listing it as a "side project," frame it as a Production-Grade Prototype / Reference Architecture.
Example Resume Formatting:

    Enterprise Agentic Data Platform & LLMOps Reference Architecture

        Architecture & Orchestration: Built a multi-agent system combining LangChain/Python, DuckDB, and dbt to execute complex financial and operational queries across structured medallion datasets and unstructured documentation.

        SQL & Data Modeling: Engineered Silver/Gold analytical data models optimized for LLM schema inspection, reducing SQL generation hallucinations and join errors.

        LLMOps & Evaluation: Implemented an automated testing framework using DeepEval and Langfuse integrated into GitHub Actions CI/CD pipelines, tracking SQL execution correctness (>92% pass rate), faithfulness, and trace latency.

        Infrastructure & Tooling: Containerized application workflows with Docker and deployed serverless microservices via GCP Cloud Run, utilizing Google AI Studio for cost-efficient inference.

How to Speak About It in an Interview

When asked about the project, ground it in software engineering discipline:

    "Anybody can wire up an LLM to an API key and call it an agent. I wanted to build a system that reflects enterprise data engineering standards. I leveraged my background in SQL data modeling to build clean dbt Gold schemas. Then, I wrapped the SQL engine in an agentic orchestrator with strict evaluation suites—measuring SQL execution accuracy, faithfulness, and latency in CI/CD before any code hits production."
