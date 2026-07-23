# Sonuç Raporu

Dökümantasyonun 7. bölümünde istenen üç başlık: araç/model seçim gerekçesi,
benchmark sonuçları ve "yapay zeka ajanı tek başına yeterli mi" değerlendirmesi.

---

## 1. Hangi araçları ve modelleri neden seçtim

### Dil modeli: `qwen3.6:35b-a3b` (varsayılan), `qwen2.5-coder:7b` (referans)

Dökümantasyon Qwen2.5-Coder'ı öneriyordu; onu koruyup üstüne daha güçlü bir
varsayılan koydum.

| Model | Neden |
|---|---|
| **`qwen3.6:35b-a3b`** — varsayılan | MoE mimarisi: 35B toplam parametre ama token başına ~3B aktif. 48 GB RAM'li M4 Pro'da 35B sınıfı kalite, 7B'ye yakın hız. Ayrıca `tools` ve `thinking` yetenekleri var; `reasoning=False` ile düşünme kapatılıp doğrudan cevap alınıyor. |
| `qwen2.5-coder:7b-instruct-q4_K_M` | Dökümantasyonun referans modeli. Karşılaştırma tabanı olarak korundu, ayar değişikliği gerektirmeden seçilebiliyor. |
| `qwen3.5:9b` | Orta nokta; 7B ile 35B arasındaki farkın modelden mi ölçekten mi geldiğini ayırmak için. |

Model adı **hiçbir yerde sabit değil**; `settings.llm_model` üzerinden okunuyor
ve kullanıcı bazında geçersiz kılınabiliyor. Benchmark harness'ının aynı kod
üzerinde model değiştirebilmesi buna bağlı.

**Neden yerel, neden bulut değil:** İncelenen kod şirket içi kaynak koddur.
Bulut API'sine göndermek, taranan secret'ların üçüncü tarafa gitmesi demektir —
"secret sızıntısı arayan" bir aracın kendisinin sızıntı yolu olması kabul
edilemez.

### Statik analiz araçları

| Araç | Kapsam | Seçim gerekçesi |
|---|---|---|
| **Ruff** | Python lint + güvenlik (`S` = flake8-bandit) | Rust ile yazıldığı için çok hızlı; tek araçta hem kalite hem güvenlik kuralları. |
| **Bandit** | Python güvenlik | Dökümantasyonda adı geçiyor. Ruff'ın `S` kuralları bandit'i kopyalar ama bandit CWE eşlemesi ve güven derecesi verir — bu ikisi **birbirini doğrular**, ki hibrit yaklaşımın çekirdeği bu. |
| **ESLint + eslint-plugin-security** | TypeScript/JavaScript | Dökümantasyonda adı geçiyor. `tools/eslint/` altında izole bir zincir olarak kuruldu; incelenen proje kendi config'ini getirse bile kural kümesi sabit kalıyor. |
| **tree-sitter** | AST | Hata toleranslı: sözdizimi bozuk dosyada bile kısmi ağaç verir. Hem metrik (fonksiyon uzunluğu, iç içe geçme) hem de fonksiyon sınırında bölme için kullanılıyor. |
| **secret-scanner** (kendi yazdığım) | Kimlik bilgisi sızıntısı | Hazır araç yerine yazdım çünkü sağlayıcı deseni + entropi eşiğinin birlikte çalışması gerekiyordu ve eşiği ölçüp ayarlayabilmem lazımdı. ~200 satır, tamamen deterministik, ağ gerektirmiyor. |
| Semgrep | — | **Elendi.** Kural setleri için ağ gerekiyor ve kurulum ağır. Yerel-öncelikli olma hedefiyle çelişti. |

### Framework: LangGraph

CrewAI ve AutoGen yerine LangGraph seçildi. Gerekçe: bu problem bir *sohbet*
değil, **belirlenmiş bir boru hattı** — statik tarama → bölme → paralel inceleme
→ birleştirme → düzeltme → doğrulama. LangGraph'ın açık state grafiği ve `Send`
API'si bu akışı doğrudan ifade ediyor. CrewAI'ın konuşan ajanlar modeli burada
kontrol edilmesi zor bir dolaylılık katmanı olurdu; hangi ajanın ne zaman
çalıştığı deterministik olmalı.

---

## 2. Benchmark sonuçları

> **Durum:** Model karşılaştırmalı benchmark koşumu `benchmarks/`
> harness'ı ile tamamlandı. Aşağıdaki değerler gerçek koşumdan gelir;
> ham JSON çıktısı `benchmarks/results/` altındadır.

### Ölçüm yöntemi

Altın veri seti `samples/vulnerable/` altındaki kasıtlı hatalı dosyalardır. Her
kusur satır numarası ve kategorisiyle etiketlenir (`ground_truth.json`).

| Metrik | Nasıl hesaplanır |
|---|---|
| **Detection Rate** | Etiketli kusurlardan kaç tanesi doğru kategori ve ±3 satır toleransla bulundu |
| **False Positive Rate** | `samples/clean/` üzerinde üretilen kritik/yüksek bulgu sayısı (doğru cevap: sıfır) |
| **Fix Accuracy** | Üretilen yamanın `validated=true` alma oranı — yani yeniden ayrıştırılıp yeniden tarandığında yeni açık eklememiş ve hedeflenen kusuru gidermiş olması |
| **Latency** | Dosya başına uçtan uca süre |

### Model karşılaştırması

| Model / Sistem | Test Edilen Dil | Bulunan Hata | Yanlış Alarm | Düzeltme Başarısı | İşlem Süresi |
|---|---|---|---|---|---|
| `qwen2.5-coder:7b-instruct-q4_K_M` | Python | 14/15 (93%) | 7 | 0/1 (0%) | 103 sn |
| `qwen2.5-coder:7b-instruct-q4_K_M` | TypeScript | 13/15 (87%) | 6 | 0/2 (0%) | 56 sn |
| `qwen3.5:9b` | Python | 15/15 (100%) | 0 | 0/1 (0%) | 255 sn |
| `qwen3.6:35b-a3b` | Python | 15/15 (100%) | 1 | 1/1 (100%) | 158 sn |
| `qwen3.6:35b-a3b` | TypeScript | 14/15 (93%) | 3 | 1/2 (50%) | 81 sn |

### Yalnızca linter vs. yalnızca LLM vs. hibrit

Raporun en önemli tablosu bu — 3. bölümdeki soruyu doğrudan cevaplıyor.

| Yapılandırma | Detection Rate | False Positive | Süre |
|---|---|---|---|
| Yalnızca statik analiz (LLM kapalı) | 19/30 (63%) | 0 | 0 sn |
| Yalnızca LLM (statik kanıt verilmiyor) | 27/30 (90%) | 4 | 301 sn |
| Hibrit (mevcut sistem) | 29/30 (97%) | 4 | 299 sn |

Sayılar tezin kendisini taşıyor. **Statik analiz** hızlı ve sıfır yanlış alarmlı
ama 11 kusuru kaçırdı — hepsi anlam gerektirenler: XSS, SSRF, path traversal,
string ile kurulan SQL, yutulan exception, N+1, erişilebilirlik. Kural eşleştirme
bunları göremez. **Yalnızca LLM** 90'a çıktı ama kaçırdığı 3 kusurun ikisi tam da
statik araçların yakaladığı desenlerdi (`tls-verification-disabled@70`,
`bind-all-interfaces@81`). **Hibrit** ikisinin birleşimi olduğu için 30 kusurdan
29'unu buldu; kaçan tek kusur (`error-handling@21` — temizlenmeyen fetch) her iki
tarafça da kaçırıldı, yani hibridin kaybı iki yöntemin ortak kör noktasıyla sınırlı.

Çapraz doğrulama yanlış alarmı artırmadan kapsam ekliyor: hibrit ve yalnızca-LLM
aynı 4 yanlış alarmı verdi (statik kanıt bir bulguyu doğrulayabilir ama uyduramaz),
buna karşılık hibrit 2 kusur daha yakaladı. Statik tarama LLM ile paralel ve
milisaniyeler sürdüğü için hibridin ek maliyeti ölçülemez düzeyde (299 vs 301 sn).

Model tablosu iki şeyi daha gösteriyor: (1) model büyüdükçe yanlış alarm düşüyor
(7b'de 6-7, 9b/35b'de 0-3) ve düzeltme başarısı artıyor (35b tek çalışan yamayı
doğruladı, 7b hiçbirini). (2) MoE kazancı somut: `qwen3.6:35b-a3b` (~3B aktif)
Python'ı dense `qwen3.5:9b`'den **daha hızlı** bitirdi (158 sn vs 255 sn), aynı
%100 tespitle — CLAUDE.md'deki varsayılan model seçiminin gerekçesi.

### Tek dosyada derinlemesine tek koşum

Yukarıdaki toplu tablonun ötesinde, `vulnerable_api.py` üzerinde tek bir koşumun
bulgu akışı (`qwen3.6:35b-a3b`, Apple M4 Pro 48 GB, 4 ajan dalı) — birleştirme ve
provenance mekaniğini somutlaştırır:

| | |
|---|---|
| Ham bulgu (birleştirme öncesi) | 57 |
| Benzersiz bulgu | 16 |
| Çapraz doğrulanmış (`hybrid`) | 8 |
| Yalnızca ajan (`llm`) | 6 |
| Yalnızca statik (`static`) | 2 |
| Elenen düşük güvenli | 0 |
| Risk skoru | 100 / 100 |
| Süre | 303 sn |
| `samples/clean/` üzerinde kritik/yüksek | 0 |

Yalnızca ajanın bulduğu 6 bulgu, hibrit yaklaşımın somut kazancıdır — hiçbir
linter kuralı bunları yakalamıyor:

- Reflected XSS (`f"<h1>Results for {term}</h1>"` — Flask'ta HTML kaçışı yok)
- SSRF (kullanıcı kontrollü URL `requests.get`'e gidiyor)
- Path traversal (`os.path.join("/var/reports", name)` sınır kontrolü yok)
- 3× kaynak sızıntısı (kapatılmayan veritabanı bağlantısı ve HTTP yanıtı)

Buna karşılık statik araçların tek başına yakaladığı ve modelin bir koşumda
atladığı iki bulgu da vardı (`B501` TLS doğrulaması, `B104` tüm arayüzlere bind).
İki tarafın da kaçırdığı şeyler farklı — birleşim tekil kümelerden geniş.

---

## 3. Yapay zeka ajanı tek başına yeterli mi?

**Hayır. Ölçülebilir gerekçelerle hayır.**

### Ajanın tek başına yetersiz kaldığı yerler

**Tekrarlanabilirlik.** Linter aynı girdide her zaman aynı çıktıyı verir. Model
`temperature=0.1` ve sabit seed'e rağmen prompt'taki küçük değişikliklere
duyarlı. Bir kalite kapısı olarak kullanılacaksa bu belirsizlik tek başına
diskalifiye edicidir.

**Kategori kararsızlığı — ölçülmüş bir örnek.** İlk koşumda model `eval()`
RCE'sini, SQL injection'ı ve path traversal'ı **hepsini**
`insecure-deserialization` olarak etiketledi. Başlıklar doğruydu, kategoriler
yanlıştı. Sonuç: mükerrer bulgular birleşemedi ve liste 33 satıra şişti.
Prompt'a karıştırılan kategorileri ayıran bir tablo ekledikten sonra kategoriler
düzeldi ve aynı kod için liste **16 bulguya** indi. Model değişmedi, sadece
kısıt eklendi.

**Sahte düzeltme — ölçülmüş bir örnek.** Refactor ajanından `eval(expression)`
satırını düzeltmesi istendi. Ürettiği:

```python
tree = ast.parse(expression, mode='eval')
return str(eval(compile(tree, '<string>', 'eval')))
```

Bu **hâlâ uzaktan kod çalıştırmadır** — `__import__('os').system(...)` bir
ifadedir ve `ast.parse(mode='eval')` bunu memnuniyetle ayrıştırır. Model
notlarında "düzeltildi" dedi. Sistemin doğrulama adımı yamayı tekrar tarayıp
Bandit `B307`'nin hâlâ tetiklendiğini gördü ve yamayı **"doğrulanamadı"**
işaretledi. Aynı koşumda model SQL injection'ı hiç düzeltmediğini dürüstçe
belirtti — ama bu dürüstlüğe güvenilemeyeceği için doğrulama yine de bağımsız
olarak çalıştı.

Ajan tek başına olsaydı bu yama "düzeltildi" olarak sunulacaktı ve geliştirici
RCE'yi kapattığını sanarak birleştirecekti.

**Dil kalitesi.** Türkçe açıklamalarda modelin tekrar eden bir kusuru gözlendi:
"keyfî komutlar çalıştırma" yerine **"keyframes komutlar çalıştırma"** yazıyor.
Anlam doğru, terim bozuk. Bulgunun teknik içeriğini etkilemiyor ama rapor
doğrudan paydaşa gidecekse düzeltme gerektirir. Bu, yerel ve görece küçük bir
modelin Türkçe üretimindeki sınırın somut örneğidir.

**Halüsinasyon.** Model, gösterilmediği satırlara demirlenen bulgular üretebiliyor.
`layer_agent._validate` bunları düşürüyor ve sayıyor — bu düşürme olmasa uydurma
satır numaraları rapora girerdi.

### Statik araçların tek başına yetersiz kaldığı yerler

Linter'lar sözdizimsel desen eşleştirir; **anlam** bilmezler:

- `f"<h1>{term}</h1>"` bir linter için sadece bir f-string'dir. Bunun bir HTTP
  yanıtına gittiğini ve `term`'in `request.args`'tan geldiğini bilmez.
- Kullanıcı kontrollü URL'in `requests.get`'e gitmesi (SSRF) veri akışı analizi
  ister.
- "Bu bağlantı kapatılmıyor", "bu döngü içinde sorgu atıyor" gibi bulgular
  kodun ne yapmaya çalıştığını anlamayı gerektirir.

Ölçülen koşumda bunlar **6 bulgu** demekti; hiçbiri kural tabanlı araçlarca
yakalanmadı.

Ayrıca linter'lar bağlam körlüğünden yanlış alarm üretir: Bandit `B603`
("subprocess çağrısı") güvenli argüman listesi kullanımında bile tetiklenir.
Bu projede kataloğa müdahale edilerek bu kural LOW'a indirildi — aksi hâlde
`shell=True`'yu argüman listesine çeviren **doğru** bir düzeltme, sistemin kendi
doğrulaması tarafından regresyon sayılıyordu.

### Doğru kurgu

Kurgu "LLM mi, linter mı" değil, **ikisinin hangi rolü üstlendiğidir**:

| Rol | Kim yapar |
|---|---|
| Desen eşleştirme, kesin kural ihlali | Statik araçlar — hızlı, tekrarlanabilir, ucuz |
| Anlam, veri akışı, niyet | Ajan — kuralların kodlamadığı kusurlar |
| **Hakemlik** | Statik araçlar tekrar — ajanın iddiasını doğrular veya doğrulamaz |
| **Düzeltme doğrulaması** | Statik araçlar tekrar — yamayı yeniden tarar |

Bu projede LLM son söz sahibi değildir. Ajanın ürettiği her şey — bulgu da,
düzeltme de — deterministik bir kontrolden geçer. `origin` alanı bu hakemliğin
sonucunu taşır ve arayüzde gizlenmez: kullanıcı bir bulgunun bağımsız olarak
doğrulanıp doğrulanmadığını görür ve ona göre ne kadar şüpheci okuyacağına
kendisi karar verir.

Kısacası: **ajan kapsamı genişletir, statik araçlar güveni sağlar.** İkisi
olmadan üretimde kullanılabilir bir kod inceleme sistemi çıkmaz.

---

## 4. Bilinen sınırlar

Dürüstlük adına, bu prototipin yapmadıkları:

- **Dinamik analiz yok.** Bu bilinçli bir güvenlik kararı (incelenen kod asla
  çalıştırılmaz), ama runtime'a bağlı açıkların görülemediği anlamına da gelir.
- **Dosyalar arası analiz yok.** Her dosya kendi bağlamında incelenir; A
  dosyasındaki bir fonksiyonun B dosyasında güvensiz çağrıldığını görmez. Bunun
  için çağrı grafiği veya code embedding tabanlı retrieval gerekir.
- **Yalnızca ilerleme akışı geçici.** WebSocket olayları tekrar oynatılmaz;
  geç bağlanan istemci önceki aşamaları kaçırır. Otoritatif sonuç her zaman
  veritabanındadır, dolayısıyla veri kaybı değil, yalnızca canlı görünüm kaybıdır.
- **Refactor dosya başına çalışır.** Birden çok dosyaya yayılan bir düzeltme
  (ör. bir imzayı değiştirip tüm çağıranları güncellemek) üretilemez.
- **Atıf belirsizliği.** Aynı kusuru birden çok ajan bulduğunda hangisinin
  yazısının gösterileceği bir seçim problemi. İlk koşumda `eval` RCE'si
  *"DatabaseAgent · kalite"* olarak atfedildi — doğru bulgu, yanıltıcı kaynak.
  Birleştirme mantığı, bulgunun niteliğine uyan lensi tercih edecek şekilde
  düzeltildi (güvenlik kategorisi → güvenlik lensi).
- **Süre.** Yerel 35B model ile dosya başına ~80-160 sn (dosya boyutuna göre),
  tam `samples/vulnerable` seti ~300 sn. CI kalite kapısı olarak kullanılacaksa
  ya daha küçük model ya da daha güçlü donanım gerekir; dosya sayısı tavanı ve
  `--languages` gibi kapsam bayrakları bu yüzden ayarlanabilir bırakıldı.
