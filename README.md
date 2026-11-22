# Study Assistant

A question-answering API over my own study notes. Ask a question in plain English and it finds the relevant notes with semantic search, has Claude answer using only those notes, and cites which notes it used. It's built around a production-style request pipeline: guardrails, a semantic cache, graceful failure, streaming, and per-request cost and latency logging.

Built as the capstone for Phase 11 (LLM Engineering) of [AI Engineering from Scratch](https://aiengineeringfromscratch.com).

## How a request flows

```
POST /ask
   │
   ▼
1. Input guard     block prompt-injection patterns, redact SSNs / cards / emails
   │
   ▼
2. Semantic cache  similar question asked before (cosine ≥ 0.92)? → return saved answer, 0 tokens
   │ miss
   ▼
3. Retrieve        embed the question, score every note chunk, take the top 3
   │
   ▼
4. Claude          answer from the notes only, cite [n], say "That's not in my notes" if missing
   │               (3 retries with backoff, 30s timeout, polite fallback message on failure)
   ▼
5. Output guard    block dangerous content (e.g. DROP TABLE, rm -rf /)
   │
   ▼
6. Cache + log     save the answer, write one JSON log line: tokens, cost, latency, cache hit
```

If the cache or the search fails, the request continues without it instead of crashing.

## Features

- **RAG with citations** over a markdown notes file, using a local embedding model (`BAAI/bge-small-en-v1.5`, runs on CPU, no embedding API needed)
- **Semantic cache** keyed by embedding similarity, so paraphrased questions hit
- **Input and output guardrails** (regex-based injection blocking and PII redaction; redacted text is what gets logged)
- **Streaming** responses via `/ask/stream`
- **Observability**: structured JSON logs per request, plus `/stats` with p50/p99 latency, cache hit rate, block count, error count, and total cost
- **Eval suite** that scores retrieval, answer correctness (LLM-as-judge), and refusals separately

## API

| Method | Path | Description |
|---|---|---|
| POST | `/ask` | `{"question": "..."}` → answer plus its full request log |
| POST | `/ask/stream` | Same, but the answer streams back as plain text |
| GET | `/health` | Service status and model |
| GET | `/stats` | Latency percentiles, cache hit rate, blocks, errors, cost |

Interactive docs are at `http://127.0.0.1:8000/docs` once the server is running.

## Running it

Requires Python 3.12 and an Anthropic API key.

```bash
git clone <this-repo-url>
cd study-assistant
python -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

The CPU-only torch install is optional but avoids a multi-GB GPU download.

Set your environment variables (see `.env.example`):

```bash
cp .env.example .env
# edit .env with your key, model ID, and your model's per-million-token prices
set -a; source .env; set +a
```

Start the server:

```bash
python -m app.api
```

Try it:

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I stop a chatbot from getting expensive?"}'

curl -N -X POST http://127.0.0.1:8000/ask/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "What is context engineering?"}'
```

To use your own notes, replace `data/notes.md`. Separate ideas with blank lines; each paragraph becomes one searchable chunk.

## Evaluation

```bash
python -m evals.eval_rag
```

The suite runs 8 answerable and 2 unanswerable questions and measures three things separately, so a failure points to the part that needs fixing:

| Metric | Before | After |
|---|---|---|
| Retrieval (right note in top 3) | 7/8 | 8/8 |
| Answers scored 4+ by the judge | 7/8 | 8/8 |
| Correct refusals on unanswerable questions | 2/2 | 2/2 |

The first run caught a retrieval miss: "Where should important information go in a long prompt?" didn't find the lost-in-the-middle note, so the app correctly answered "That's not in my notes." Checking the ranking showed markdown headings were being indexed as their own near-empty chunks, and one outranked the right note. Excluding headings from chunking fixed it without increasing prompt size.

The judge is a second Claude call that grades each answer against expected key points using an anchored 1–5 rubric, returned through a forced tool call so the score is always a clean integer. Ten cases is a smoke test, not a statistically meaningful benchmark.

## Project structure

```
app/
  search.py      chunking, embeddings, semantic search
  assistant.py   guardrails, cache, pipeline, streaming, logging, stats
  api.py         FastAPI endpoints
evals/
  eval_rag.py    retrieval / judge / refusal evaluation
data/
  notes.md       the knowledge base
```

## Limitations and next steps

Measured against a 15-point production checklist, this covers 11. What's missing, and how I'd add it:

- **Rate limiting per user**: add an API key or user ID to requests and a token-bucket limiter (e.g. per-user requests per minute).
- **Fallback model chain**: on repeated failures, retry the request with a smaller or different model before showing the fallback message.
- **Load testing**: run concurrent requests (e.g. with Locust or k6) and track p99 latency under load. The current endpoints are synchronous, so an async client would be the first change.
- **Deployment**: containerize with Docker and deploy to a public host.

Other known limits:

- Regex guardrails only catch obvious attacks; rephrased prompt injection gets through.
- With streaming, the output guard runs after the text has already been shown. It can stop the answer from being cached and flag it in the log, but it can't un-show it.
- The cache and note vectors live in memory and reset when the server restarts. A vector database or Redis would make them persist.
- Notes are re-embedded on every startup, which is fine for a small file but wouldn't scale.

## MCP server

The notes search is also available as an MCP server, so MCP clients like Claude Code can search and quiz from the notes directly.

| Primitive | Name | What it does |
|---|---|---|
| Tool | `notes_search(query, top_k)` | Semantic search over the notes, returns passages with scores |
| Tool | `notes_list_sections()` | Lists the topics the notes cover |
| Resource | `notes://all` | The full notes file, for attaching to a conversation |
| Prompt | `quiz_me(topic)` | Searches the notes, then quizzes you one question at a time |

Tools are read-only and annotated as such; arguments are validated with typed, bounded schemas, and invalid calls come back as tool errors the model can correct.

Connect it to Claude Code:

```bash
claude mcp add study-notes -- /path/to/.venv/bin/python /path/to/study-assistant/mcp_server.py
```

Or run the demo client, which launches the server over stdio and calls each primitive:

```bash
python mcp_client_demo.py
```