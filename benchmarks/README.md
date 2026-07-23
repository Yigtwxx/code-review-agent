# Benchmark harness

Model karşılaştırma ve "yalnızca linter vs. yalnızca LLM vs. hibrit" ölçümü.
`docs/sonuc-raporu.md` Bölüm 2'deki tabloları besler.

## Ne ölçülür

| Metrik | Nasıl | Kod |
|---|---|---|
| **Detection Rate** | Etiketli kusurlardan kaçı doğru kategori + ±3 satır toleransla bulundu | `metrics.detection` |
| **False Positive** | `samples/clean/` üzerinde üretilen CRITICAL/HIGH bulgu sayısı (hedef 0) | `metrics.false_positives` |
| **Fix Accuracy** | Üretilen yamanın `validated=true` oranı | `metrics.fix_accuracy` |
| **Latency** | Dosya başına uçtan uca süre (`review_graph.ainvoke`) | `runner.run_graph` |

Altın veri seti: `samples/vulnerable/ground_truth.json` — her kusur satır aralığı ve
`app.schemas.finding.Category` slug'ıyla etiketli. Slug geçersizse yükleme hata verir.

## Üç mod

- `static` — yalnızca deterministik analizörler (model yok, graph yok).
- `llm` — tam graph ama `disable_static=True`: model statik kanıt görmeden inceler.
- `hybrid` — üretim davranışı: statik kanıt ajanı besler ve iddiasını çapraz doğrular.

`disable_static` yalnızca benchmark ölçümü içindir; üretimde hibrit çapraz doğrulama
her zaman açıktır.

## Çalıştırma

Repo kökünden, backend uv ortamıyla çalıştırılır (langgraph, ollama vb. oradadır):

```bash
# tam matris + raporu güncelle
uv run --project backend python -m benchmarks.run --update-report

# hızlı doğrulama: tek model, tek dil, config tablosu atla
uv run --project backend python -m benchmarks.run \
  --models qwen2.5-coder:7b-instruct-q4_K_M --languages python --skip-config

# yalnızca config tablosu (varsayılan 35b)
uv run --project backend python -m benchmarks.run --skip-models
```

Ollama'nın çalışıyor ve modellerin `ollama pull` ile çekilmiş olması gerekir.

## Çıktı

- `benchmarks/results/<timestamp>.json` — ham sonuç (git'e girmez).
- `benchmarks/results/<timestamp>.md` — okunur özet.
- `--update-report` verilirse `docs/sonuc-raporu.md` tabloları yerinde doldurulur.

## Dosyalar

| Dosya | Sorumluluk |
|---|---|
| `schema.py` | Ground-truth + sonuç Pydantic modelleri, slug doğrulama |
| `metrics.py` | Saf metrik fonksiyonları (I/O yok, birim test edilebilir) |
| `runner.py` | Graph'ı DB'siz çağırır; static/llm/hybrid modları |
| `run.py` | CLI, matris orkestrasyonu, sonuç yazımı |
| `report_writer.py` | Sonuçtan markdown tablo üretimi + rapora splice |
