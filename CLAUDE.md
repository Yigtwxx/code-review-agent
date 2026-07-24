# Code Review Agent

Agent-based code review and security analysis system. Submitted code is partitioned
into architectural layers (Frontend / Backend / Database / Config-Infra), each layer
is reviewed by a dedicated LangGraph agent under a **security** and a **quality**
lens, every agent finding is cross-validated against deterministic static analysis,
and verified refactored code (`refactored_code`) is produced. Results are presented
as inline comments in a GitHub pull-request-style web UI.

The source assignment brief is not part of the repository (`*.pdf` is gitignored).

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 (uv), FastAPI, LangChain + LangGraph, Beanie + Motor |
| LLM | Ollama (local) — default `qwen3.6:35b-a3b`, alternative `qwen2.5-coder:7b-instruct-q4_K_M` |
| Static analysis | Ruff, Bandit, ESLint (+ eslint-plugin-security), tree-sitter, custom secret scanner |
| Database | MongoDB 7 (Docker Compose) |
| Frontend | Next.js 16 App Router, TypeScript `strict`, Tailwind 4, Shiki |
| Realtime | FastAPI WebSocket |

## Commands

```bash
# Infrastructure. Skip if a local mongod already listens on 27017 — two instances
# on the same port conflict, and `localhost` resolves to the host one.
docker compose up -d mongo

# Backend. Port 8001 rather than the uvicorn default 8000, which is reserved
# for another service in this environment.
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8001

# Frontend
cd frontend && npm run dev

# Verification
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npx tsc --noEmit && npx eslint src && npm test
```

## Architecture

```
ingest → static_scan → partition → injection_guard → supervisor
                                                        ├─ FrontendAgent  (security + quality)
                                                        ├─ BackendAgent   (security + quality)
                                                        ├─ DBAgent        (security + quality)
                                                        ├─ ConfigAgent    (security + quality)
                                                        └─ GenericAgent   (security + quality)
                                                        ↓
              aggregate → hallucination_check → refactor → validate → report
```

Every node emits progress events over the WebSocket (`node_started`,
`finding_found`, `node_finished`).

Full rationale: [`docs/architecture.md`](docs/architecture.md).

## Architectural rules

- LangGraph nodes live under `backend/app/agents/nodes/` — one file, one
  responsibility per node.
- Prompts are **never inlined in code** — they belong in `backend/app/prompts/*.jinja2`.
- Model names are **never hardcoded** — always read through `settings.llm_model`.
- LLM calls are wrapped in `tenacity` retry with backoff; `temperature=0.1` plus
  enforced JSON schema output (determinism — see "Determinism in Code Generation"
  in `docs/keywords.md`).
- All agent output conforms to the Pydantic `Finding` schema. Free-form text
  without a schema is not accepted.
- LLM findings are cross-validated against static analysis results
  (`corroborated_by_static`). Hybrid validation is the primary mechanism for
  eliminating hallucinations and must not be bypassed.
- MongoDB queries **always** carry a `user_id` filter (IDOR protection),
  enforced in a single place: `app/auth/deps.py`.

## Security

- **Submitted code is never executed.** Parsing and static analysis only.
- ZIP extraction rejects zip-slip (`../`) entries and enforces limits on entry
  count and uncompressed size.
- Secrets come exclusively from the environment (`pydantic-settings`); `.env`,
  `*.pem` and `*.key` are gitignored; credentials are never written to logs at
  any level.
- User code is passed to the LLM as **data**, not instruction. The
  `injection_guard` node is never bypassed.
- JWT: short-lived access token plus httpOnly refresh cookie; passwords hashed
  with argon2.
- Per-user GitHub tokens are encrypted at rest in MongoDB with Fernet.

## Code style

- **Python:** type annotations required, `ruff format` (88 columns), `X | None`
  (not `Optional`), f-strings, import order stdlib → third-party → local.
- **TypeScript:** `strict: true`, `any` is forbidden (use `unknown`), prefer
  `undefined` over `null`, prettier with single quotes, `async/await` rather than
  `.then()` chains.
- **Tests:** backend `backend/tests/test_*.py` (pytest), frontend `*.test.ts(x)`
  (vitest).
- Code, identifiers and comments are written in **English**. Project documentation
  under `docs/` is written in **Turkish**.

## Directory map

| Path | Contents |
|---|---|
| `backend/app/agents/` | LangGraph state, graph and nodes — the core of the system |
| `backend/app/prompts/` | Agent persona and lens prompt templates (jinja2) |
| `backend/app/static_analysis/` | Ruff / Bandit / ESLint / tree-sitter / secret-scanner wrappers |
| `backend/app/ingest/` | Upload, ZIP, paste and GitHub PR diff normalisation |
| `frontend/src/components/review/` | PR-style diff viewer and inline finding threads |
| `samples/vulnerable/` | Deliberately vulnerable fixtures (labelled in `ground_truth.json`) |
| `samples/clean/` | Hardened counterparts — the false-positive control set |
| `benchmarks/` | Model comparison harness (Detection Rate / FP / Fix Accuracy / Latency) |
| `tools/eslint/` | Isolated lint toolchain used to analyse submitted TS/JS |
| `tools/ci/` | GitHub Actions client and example workflow |
| `docs/` | Architecture, key concepts, result report |

## Environment notes

- The language model runs locally on Ollama. The default `qwen3.6:35b-a3b` is a
  MoE model (~3B active parameters), delivering 35B-class quality at close to 7B
  latency on Apple Silicon with 48 GB of unified memory.
- The system Python is 3.9; **the project pins 3.12 via uv** and never uses the
  system `python3`.
- Do not create commits, pushes or pull requests unless explicitly requested.
