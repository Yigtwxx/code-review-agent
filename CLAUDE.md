# Code Review Agent

AI ajan destekli kod inceleme ve güvenlik analiz sistemi. Yüklenen kodu katmanlara
(Frontend / Backend / Database / Config-Infra) ayırır, her katmana özel LangGraph ajanı
**güvenlik** ve **kalite** lens'leriyle inceler, statik analiz araçlarıyla çapraz doğrular
ve düzeltilmiş kod (`refactored_code`) üretir. Sonuçlar GitHub PR review ekranına benzeyen
bir web arayüzünde satır içi yorum olarak gösterilir.

Kaynak görev tanımı: `AI_Agent_Code_Review_ve_Guvenlik_Analizi_Dokumantasyonu.pdf.pdf`

## Stack

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12 (uv), FastAPI, LangChain + LangGraph, Beanie + Motor |
| LLM | Ollama (lokal) — varsayılan `qwen3.6:35b-a3b`, alternatif `qwen2.5-coder:7b-instruct-q4_K_M` |
| Statik analiz | Ruff, Bandit, Semgrep, ESLint, gitleaks, tree-sitter |
| DB | MongoDB 7 (Docker Compose) |
| Frontend | Next.js 15 App Router, TypeScript `strict`, Tailwind, shadcn/ui, Shiki |
| Realtime | FastAPI WebSocket |

## Komutlar

```bash
# altyapı — bu makinede brew mongodb-community@7.0 zaten 27017'de çalışıyor ve
# veri (code_review_agent) orada; compose mongo'yu başlatma, ikisi çakışır
docker compose up -d mongo

# backend — port 8001, uvicorn'un varsayılan 8000'i başka projeye ait
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8001

# frontend
cd frontend && npm run dev

# doğrulama
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npx tsc --noEmit && npm test
```

## Mimari

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

Her node WebSocket'e ilerleme event'i basar (`node_started`, `finding_found`, `node_finished`).

## Mimari kuralları

- LangGraph node'ları `backend/app/agents/nodes/` altında — her node tek dosya, tek sorumluluk.
- Prompt'lar **koda gömülmez** — `backend/app/prompts/*.jinja2`.
- Model adı **hardcode edilmez** — `settings.llm_model` üzerinden okunur.
- LLM çağrıları `tenacity` ile retry+backoff sarmalanır; `temperature=0.1` + JSON şema zorlaması
  (determinizm — bkz. `docs/keywords.md` "Determinism in Code Generation").
- Tüm ajan çıktıları Pydantic `Finding` şemasına uyar; şemasız serbest metin kabul edilmez.
- LLM bulguları statik analiz bulgularıyla çapraz doğrulanır (`corroborated_by_static`) —
  hibrit doğrulama halüsinasyonu elemenin birincil mekanizması, atlanmaz.
- MongoDB sorguları **daima** `user_id` filtresi içerir (IDOR koruması) — tek nokta: `app/auth/deps.py`.

## Güvenlik

- **Analiz edilen kod asla çalıştırılmaz.** Yalnızca parse + statik analiz.
- ZIP açarken zip-slip (`../`) koruması, boyut ve dosya sayısı limiti zorunlu.
- Secret'lar yalnızca env'den (`pydantic-settings`); `.env`, `*.pem`, `*.key` gitignore'da;
  log'a hiçbir seviyede credential basılmaz.
- Kullanıcı kodu LLM'e **veri** olarak verilir; `injection_guard` node'u bypass edilmez.
- JWT: kısa ömürlü access token + httpOnly refresh cookie; parola hash'i argon2.
- Kullanıcının GitHub token'ı MongoDB'de Fernet ile şifreli tutulur.

## Kod stili

- **Python:** tip anotasyonu zorunlu, `ruff format` (88 karakter), `X | None` (`Optional` değil),
  f-string, import sırası stdlib → third-party → local.
- **TypeScript:** `strict: true`, `any` yasak (`unknown` kullan), `undefined` tercih,
  prettier tek tırnak, `async/await` (`.then()` zinciri değil).
- **Testler:** backend `backend/tests/test_*.py` (pytest), frontend `*.test.ts(x)` (vitest).
- Kod, identifier ve yorumlar **İngilizce**; döküman ve rapor **Türkçe**.

## Dizin haritası

| Yol | İçerik |
|---|---|
| `backend/app/agents/` | LangGraph state, graph, node'lar — sistemin çekirdeği |
| `backend/app/prompts/` | Ajan persona ve lens prompt template'leri (jinja2) |
| `backend/app/static_analysis/` | Ruff/Bandit/Semgrep/ESLint/gitleaks/tree-sitter sarmalayıcıları |
| `backend/app/ingest/` | Upload, ZIP, paste, GitHub PR diff normalizasyonu |
| `frontend/components/review/` | PR-benzeri diff görüntüleyici ve bulgu thread'leri |
| `samples/vulnerable/` | Kasıtlı hatalı örnek kodlar (+ `ground_truth.json` etiketleri) |
| `samples/clean/` | Temiz karşılıklar — false positive kontrolü için |
| `benchmarks/` | Model karşılaştırma harness'ı (Detection Rate / FP / Fix Accuracy / Latency) |
| `docs/` | Mimari, 15 anahtar kelime, sonuç raporu |

## Notlar

- Donanım: Apple M4 Pro, 48 GB RAM. Ollama lokal çalışır; `qwen3.6:35b-a3b` MoE olduğu için
  (~3B aktif parametre) 35B kalitesini 7B'ye yakın hızda verir.
- Sistem Python'ı 3.9 — **uv ile 3.12 pinlenmiştir**, sistem `python3`'ü kullanılmaz.
- Kullanıcı açıkça istemedikçe commit / push / PR açılmaz.
