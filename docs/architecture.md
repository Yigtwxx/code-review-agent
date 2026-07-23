# Mimari

## Genel bakış

Sistem üç parçadan oluşur: bir FastAPI backend (analiz motoru), bir Next.js
arayüz (GitHub PR incelemesine benzeyen sunum katmanı) ve MongoDB (kullanıcı
başına veri). Dil modeli **yerelde** Ollama üzerinde çalışır; kod hiçbir zaman
makineden çıkmaz.

```
┌──────────────┐   REST + WebSocket   ┌──────────────┐   HTTP   ┌────────┐
│ Next.js UI   │ ───────────────────► │ FastAPI      │ ───────► │ Ollama │
│ (TS, strict) │ ◄─────────────────── │ + LangGraph  │ ◄─────── │ (yerel)│
└──────────────┘                      └──────┬───────┘          └────────┘
                                             │ Beanie
                                       ┌─────▼─────┐
                                       │ MongoDB 7 │
                                       └───────────┘
```

## İnceleme boru hattı

Çekirdek `backend/app/agents/graph.py` içindeki LangGraph grafiğidir. İki ayrı
fan-out noktası vardır ve ikisi de dinamiktir — dal sayısı gönderilen koda göre
belirlenir.

```
                    ┌─────────────┐
   upload / PR ────►│   ingest    │  SourceFile[] (yol, içerik, dil, diff hunk)
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │ static_scan │  Ruff + Bandit + ESLint + secret-scanner
                    └──────┬──────┘  + tree-sitter → deterministik Finding[]
                           ▼
                    ┌─────────────┐
                    │  partition  │  yol + import + AST sinyali → katman
                    └──────┬──────┘  (bir dosya birden çok katmana düşebilir)
                           ▼
                    ┌─────────────┐
                    │  injection  │  koda gizlenmiş "AI reviewer: ..." metinleri
                    │   _guard    │  → hem ajana bildirilir hem bulgu olur
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │ supervisor  │  Send() ile paralel fan-out
                    └──┬───┬───┬──┘
        ┌──────────────┘   │   └──────────────┐
        ▼                  ▼                  ▼
  FrontendAgent      BackendAgent          DBAgent    ConfigAgent   GenericAgent
  ├ security         ├ security            ├ security ├ security    ├ security
  └ quality          └ quality             └ quality  └ quality     └ quality
        └──────────────┬──────────────────┘
                       ▼
                ┌─────────────┐
                │  aggregate  │  (dosya, kategori) + satır aralığı örtüşmesiyle
                └──────┬──────┘  kümele → statik kanıtla çapraz doğrula
                       ▼
                ┌──────────────┐
                │ hallucination│  düşük güvenli + desteksiz bulguları ele,
                │    _check    │  var olmayan paketleri PyPI/npm'e sor
                └──────┬───────┘
                       ▼
                ┌─────────────┐
                │  refactor   │  dosya başına bir dal, en riskli 10 dosya
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │  validate   │  yamayı tekrar ayrıştır + tekrar tara
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │   report    │  risk skoru + dağılımlar
                └─────────────┘
```

Her node giriş ve çıkışında WebSocket'e olay basar. Grafik **MongoDB'ye
dokunmaz**; kalıcılık `backend/app/services/reviews.py` içindedir. Bu ayrım
sayesinde grafik testlerde ve (akşam yapılacak) benchmark koşumlarında
veritabanı olmadan çalıştırılabilir.

## Hibrit doğrulama — sistemin ana fikri

Dökümantasyonun temel endişesi LLM halüsinasyonuydu. Cevabımız, modele
güvenmemek üzerine kurulu üç kademeli bir mekanizmadır.

**1. Statik analiz önce çalışır ve ajana kanıt olarak verilir.**
Ajan boş sayfayla başlamaz; o dosyada Bandit/Ruff/ESLint ne bulduysa görür.
Prompt bunu açıkça "bunlar gerçektir, öneri değil" diye niteler ve ajandan
katma değer ister: işaretlenen satırdaki verinin gerçekten saldırgan kontrolünde
olup olmadığı, birden çok satıra yayılan kusurlar, hiçbir kuralın kodlamadığı
sorunlar.

**2. Bulgular çapraz doğrulanır.**
`aggregate` node'u aynı kusuru anlatan bulguları kümeler. Bir ajan bulgusunu
bağımsız bir araç da doğruladıysa `origin` **`hybrid`** olur, güveni artar ve
arayüzde *"bandit:B608, ruff:S608 doğruladı"* rozetiyle görünür. Hiçbir aracın
desteklemediği bulgu `llm` kalır ve *"statik doğrulama yok"* etiketi taşır.

Kümeleme satır *aralığı örtüşmesine* bakar, yalnızca başlangıç satırına değil:
linter kusurlu ifadeyi gösterirken ajan çoğu zaman içindeki fonksiyonun tamamını
raporlar. Sadece `line_start` karşılaştırmak bunları iki ayrı bulgu sayardı.

**3. Desteksiz ve düşük güvenli bulgular elenir.**
`hallucination_check`, hiçbir aracın doğrulamadığı **ve** modelin kendi güveni
0.45 altında olan bulguları düşürür. Elenen sayı gizlenmez;
`suppressed_low_confidence` olarak rapora yazılır.

Provenance alanları modelin kendi hakkında iddia edebileceği şeyler değildir —
`origin`, `agent`, `corroborated_by` alanlarını biz doldururuz. Modelin
şemasında (`LlmFinding`) bu alanlar yoktur.

## Katman ataması neden LLM'siz

`backend/app/agents/partition.py` tamamen deterministiktir: önce yol deseni
(`components/` → frontend, `migrations/` → database), sonra içerik sinyali
(`from fastapi` → backend, ham `SELECT` → database).

Gerekçe: sınıflandırmayı modele yaptırmak, asıl modele ihtiyaç duyulan işten
önce yavaş ve tekrarlanamaz bir adım eklerdi. Aynı incelemenin iki koşumu
**hangi ajanların çalıştığı konusunda bile** anlaşmazlığa düşerdi.

Bir dosya birden fazla katmana düşebilir. Gerçek koşumda `vulnerable_api.py`
hem `backend` (Flask route'ları) hem `database` (ham SQL) olarak sınıflandı ve
dört ajan dalı çalıştı; mükerrer bulgular `aggregate` içinde birleşti.

## Güvenlik kararları

İncelenen kod güvenilmez girdidir. Kendi kodumuzun taşıdığı kurallar:

| Karar | Gerekçe |
|---|---|
| **Kod asla çalıştırılmaz** | Onu çalıştırmak, saldırgana sunucumuzda RCE vermektir. Yalnızca ayrıştırma ve statik tarama. |
| ZIP'te zip-slip reddi, boyut ve dosya sayısı tavanı | `../` içeren girdiler sanitize edilmez, reddedilir; sıkıştırılmamış toplam boyut da sınırlıdır (zip bomb). |
| Prompt injection guard atlanmaz | İncelenen kod prompt'ta veri olarak sınırlandırılır **ve** şüpheli satırlar bulgu olarak raporlanır. |
| Erişim tek noktadan | `auth/deps.py::get_owned_review`. Başkasının incelemesi 403 değil **404** döner — id'nin varlığı bile sızdırılmaz. |
| Token bellekte | Access token `localStorage`'a yazılmaz; sayfa yenilendiğinde httpOnly refresh cookie'sinden geri alınır. |
| GitHub token'ı şifreli | Fernet ile; anahtar yoksa saklamak **reddedilir**, açıkta yazılmaz. |

## Kalıcılık modeli

| Collection | İçerik | Index |
|---|---|---|
| `users` | hesap, tercihler, şifreli GitHub token | `email` (unique) |
| `reviews` | koşum, durum, risk skoru, istatistikler | `user_id + created_at` |
| `review_files` | gönderilen dosyalar, katman atamaları, diff hunk'ları | `review_id + path` |
| `findings` | bulgular, provenance, durum | `review_id + file_path`, `user_id` |
| `patches` | düzeltilmiş kod, diff, doğrulama sonucu | `review_id + file_path` (unique) |

## Gerçek zamanlı akış

İnceleme, WebSocket'i sunan süreçle aynı süreçte arka plan görevi olarak
çalışır; bu yüzden olay yolu bellek içi bir pub/sub'dır (`app/events/bus.py`).
Broker yok, ek hareketli parça yok.

Bilinçli kabul edilen sınır: **olaylar geçicidir ve tekrar oynatılmaz.** Geç
bağlanan istemci önceki aşamaları kaçırır. Bu kabul edilebilir çünkü otoritatif
sonuç her zaman MongoDB'deki inceleme belgesidir — arayüz WebSocket hiç
bağlanmasa da REST üzerinden doğru sonucu gösterir. Arayüz bu durumu gizlemez,
*"Bu bağlantıdan sonraki aşamalar burada görünecek"* der.

Abone kuyrukları sınırlıdır; okumayı bırakan bir sekme en eski olayları düşürür,
üreticinin belleğini şişirmez.

## Model kullanımı

Tüm çağrılar `backend/app/agents/llm.py` üzerinden geçer ve **şemayla
kısıtlanır** — model serbest metin değil, Pydantic modeline uyan JSON üretir.
Şemaya uymayan yanıt ayrıştırılmaya çalışılmaz, `tenacity` ile yeniden denenir.

- `temperature=0.1`, sabit `seed` → tekrarlanabilirlik
- `num_predict` her zaman açıkça verilir (refactor için ayrı, daha yüksek bütçe)
- Düşünen modellerde `reasoning=False`; desteklemeyen modelde bu bayrak
  gönderilmez (Ollama `/api/show` ile yetenek sorgulanır)
- Eşzamanlı ajan sayısı `max_concurrent_agents` ile sınırlı — yerel çalışan tek
  bir runtime'ı boğmamak için

Model adı hiçbir yerde sabit değildir; `settings.llm_model` üzerinden okunur ve
kullanıcı bazında geçersiz kılınabilir. Benchmark harness'ının model
değiştirebilmesi buna bağlıdır.
