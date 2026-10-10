# DESIGN

> Copy this file to `DESIGN.md` and answer it **before you write code**. Revise it as you
> learn, but keep the first version in git history. A stranger grades it (`G-DESIGN`), so
> write for someone who has never seen your code. The five headings are fixed; keep them.

## Components

What are the moving parts, and which of them are separate processes? Name each one and its
port. Why are the Judge and Masker separate services while the Guardrail runs in-process?
Answer in your own words, not SPEC's.

Moving Parts: CLI, Pipeline, ADK LLM Agent, Sanitizer, Security Judge, Guardrail, Masker, Postgres SQL, MCP Tollbox Server, Arize Phoenix, Eval Runner, Mem0.

I think all of them are separate processes.

Judge checks if an input is hostile while Masker checks data leakage. They are separate services because they take care of different things.

The Guardrail runs in-process because it checks if a query falls out of time range, and running in-process can make sure the evaluation is run fast.

## Responsibilities

Which component decides that a customer may only see their own orders, and where exactly is
that line of code or SQL? Which component may hold an API key? Which one decides a turn is
over budget? For every rule in SPEC §11, say whether it is enforced **in code**, **in a
prompt**, or **both**, and why. This table is the core of `G-ENFORCE`.

See their own orders: MCP Toolbox Server and Session Initialization Code.

Line: In tools.yaml, WHERE order_id = $1 AND customer_email = $2

Hold an API key: The Local Backend System Environment

Decides a turn is over budget: Pipeline Module

R-1: Code. Enforced via SQL

R-2: Code. Using pipeline python file to trigger vector memory retrieval before calling an agent.

R-3: Code. Discard retrieved memory whose similarity scores fall below T-MEM-MINSCORE.

R-4: Code. It's pipeline logic, which saves only user input to Mem0.

R-5: Code. Crease a memory.recall trace span of type RETRIEVER.

R-6: Prompt. It's a guardrail agent prompt.

R-7: Both. Uses code to enforce string length caps to prevent infinite Mem0 loop. Uses prompt to instruct the model to extract clean facts.

R-8: Code. Strip memory tools from the main LLM agent toolset so all memory operations are controlled by pipeline steps.

R-9: Code. Defaults to blocking execution if Security Judge Service crashes, times out or returns invalid JSON.

## Communication

How does a message travel from the CLI or browser to the database and back? Name each hop's
protocol (function call, MCP, A2A JSON-RPC, HTTP, NDJSON). Which A2A method did you
implement, and what does a verdict look like on the wire?

1. **Client Submission to Pipeline:**
  - **Browser --> Web Server (**`support/web.py`**):** **HTTP POST** (`/api/chat` carrying a JSON body).
  - **CLI --> Pipeline (**`support/pipeline.py`**):** **In-Process Function Call** (invoking `run_pipeline(...)` async generator).
2. **Sanitizer Verification:**
  - **Pipeline --> Sanitizer (**`guards/sanitizer.py`**):** **In-Process Function Call** (standard Python regex/string cleaning).
3. **Threat Analysis (Judge Service):**
  - **Pipeline --> Security Judge (**`:10002`**):** **A2A JSON-RPC over HTTP** (POST request carrying JSON-RPC payload to evaluate injection risk).
4. **Domain Scope Verification (Guardrail):**
  - **Pipeline --> Guardrail Agent:** **In-Process Function Call** (executing the local ADK `LlmAgent` session runner).
5. **Memory Retrieval:**
  - **Pipeline --> Mem0 Cloud API:** **HTTPS REST API** (queries vector storage for past context scores).
6. **Agent Processing & Tool Execution:**
  - **Pipeline --> Google Gemini API:** **HTTPS REST API** (via `google-adk` runner).
  - **Gemini Agent --> MCP Toolbox Server (**`:5000`**):** **MCP over HTTP** (POST to `/api/tool/get-order-status/invoke` with bound session parameters).
7. **Database Querying & Return:**
  - **MCP Toolbox --> PostgreSQL (**`:5432`**):** **PostgreSQL Native Wire Protocol** (TCP socket parameterized query execution).
  - **PostgreSQL --> MCP Toolbox:** Native SQL record tuple response.
  - **MCP Toolbox --> Agent/Pipeline:** **HTTP JSON Response** returning nested JSON strings: `{"result": "{\"order_id\": 3, ...}"}`.
8. **Response Masking & Persistence:**
  - **Pipeline --> Masker Service (**`:10003`**):** **A2A JSON-RPC over HTTP** (submits model reply to redact PII).
  - **Pipeline --> Mem0 Cloud API:** **HTTPS REST API** (persists safe user query to long-term memory).
9. **Response Delivery to User:**
  - **Pipeline --> Web Browser:** **NDJSON over HTTP** (`StreamingResponse` emitting line-delimited `application/x-ndjson` events in real time).
  - **Pipeline --> CLI:** **In-Process Async Generator Yield / Console Print**.



### The A2A method:

The system implements the `message/send` method (or `tasks/send`) of the standard Agent-to-Agent (A2A) protocol over JSON-RPC 2.0.

The verdict would look like Allow or Block.

## State

What is stored, where, and for how long: sessions, memories, traces, run logs, the action
log? Which of them contain customer data, and who can read each one? What happens to
memory when a customer's order changes after the memory was saved?

Sessions: Stored in memory by ADK's InMemorySessionService. Stores active user's conversation history and bound session parameter. When the applicaiton process terminates, the session state is destroyed.

Memories: Extracted from user queries and sent to Mem0 Cloud. Will persist indefinitely  unless explicitly cleared via Mem0 API.

Traces: Posted to Arize Phoenix, recording every step. Includes full user inputs, model outputs, etc. Stays even when process ends.

Run logs: Capture events, and written to disk. No user data.

Action log: PostgreSQL table. Enforce data integrity via SQL constraints.

When an order status changes, the Mem0 vector memory stays untouched.

System instructions explicitly require the agent to fetch order information solely via MCP tools, and live tool outputs returned from PostgreSQL override any conflicting textual context retried from memory.

## Trade-offs

What did each guard cost you in latency (from your traces), and was it worth it? Did you
make the Guardrail fail closed, and what does that cost when Gemini is slow? If you changed
`T-MEM-MINSCORE` or argued against any threshold, give the evidence here, and keep the
original gate in your report.



Sanitizer: <5 ms. Yes. It will drop obvious SQL script injections.

Security Judge: 80-150 ms if patterns match and 450-700 ms if LLM fallbacks.

Guardrail: 500-850 ms.

Masker: 400-750 ms.