# Veri ve model görevi — uygulama planı

**Sorumlu:** Saib Alsaeid (veri ve model birinciliği)
**Kapsam:** COCO veri seti, RF-DETR Nano eğitimi, manuel olay referansı, deney kayıtları
**Donanım (ESP32/OLED) kapsam dışı bırakıldı** — yalnızca "gelecek çalışma" olarak not edilir.

**Durum (12 Kasım 2026):** Kareler çıkarıldı ✔ · Etiketleme bekliyor ✘ · GPU ortamı bekliyor ✘

---

## 0. Doğrulanmış durum

| Adım | Sonuç |
|---|---|
| TRAIN kareleri | 734 kare, 13 klip (`datasets/wall/train`) |
| TEST kareleri | 166 kare, **farklı kayıt** (`datasets/wall/test`) |
| VALID kareleri | 180 kare, 3 klip (`datasets/wall/valid`) — pilot için ayrıldı |
| Split sızıntısı | ✔ Yok (aşağıdaki kanıt) |
| Etiketleme aracı | ✔ İlk etiketlenmemiş kareden devam ediyor |
| COCO etiketlemesi | **Pilot sürüyor** — `valid` bölümünde kullanıcı etiketliyor |
| Test sayısı | 86 (78 + 8 pilot veri testi) |

### Pilot bölmesi (13 Kasım 2026)

`valid` bölümü elle kuruldu: kayıt sırasındaki ilk 3 klip (`clip_01`–`clip_03`,
her biri 60 kare) `datasets/wall/valid` altına taşındı. Kalan 13 klip `train`
bölümünde kaldı, `test` bölümüne dokunulmadı.

```powershell
.\.venv\Scripts\python.exe scripts\split_pilot.py --dataset datasets\wall --valid-clips 3 --dry-run
```

Araç **yalnızca bütün klipleri** taşır; aynı çekimin iki bölümde birden
bulunmasını reddeder ve COCO etiketlerini taşınan karelerle birlikte yeni
bölüme taşır.

> ⚠️ **Bu bölme geçicidir.** `valid` ve `train` aynı kayıttan ("How to Train on
> a Tennis Wall") gelen kliplerden oluşur; bu nedenle `valid` üzerindeki metrik
> **genellenebilirlik kanıtı değildir**, yalnızca boru hattının çalıştığını
> gösterir. Gerçek `valid` için **üçüncü bağımsız kayıt** gerekir (aşağıya bak).

### Split bütünlüğü kanıtı

`extract_frames.py` her kareyi kaynak dosyanın SHA256 önekinin ilk 16 hanesiyle adlandırır.

```
TEST  kaynağı : 4bafc320d8718ac1...  13134650_1920_1080_30fps.mp4   (53.6 MB, 82.8 s, 30 fps)
TRAIN kaynağı : 16 ayrı anahtar      -> How to Train on a Tennis Wall.mp4 (16 klip, 24 fps)

test/  166 kare  -> tamamı  4bafc320d8718ac1
valid/ 180 kare  -> 3 klip anahtarı (clip_01, clip_02, clip_03)
train/ 734 kare  -> kalan 13 klip anahtarı (baskın kayıt)
```

Kesişim yoktur. `valid` ve `train` aynı kayıttan geldiği için aralarındaki
kesişim **klip seviyesinde** sıfırdır ama **kayıt seviyesinde** yoktur; bu
nedenle pilot `valid` metriği genellenebilirlik kanıtı sayılmaz.
`test` ise farklı mekân, farklı oyuncu, farklı kamera açısıdır.

---

## 1. Bölüm ayrımı kuralı

Bölümleme **kayıt seviyesindedir**, kare seviyesinde değil.

| Kayıt | Bölüm | Durum |
|---|---|---|
| "How to Train on a Tennis Wall" (16 klip) | **train** | ✔ hazır |
| `13134650_1920_1080_30fps.mp4` | **test** | ✔ hazır |
| Kendi çekimimiz (yeni) | **valid** | ✘ **yapılacak** |

> `extract_frames.py` aynı *dosya* hash'ini iki bölüme koymayı engeller; aynı *kaydın
> farklı kliplerini* engellemez. Bu yüzden kural elle uygulanır.

### valid kaydı için çekim kuralı
- Sabit telefon, tercihen **60 fps**, 1080p
- **Farklı oyuncu ve farklı duvar** (test ve train kayıtlarından)
- En az 3–4 ayrı kayıt, en az 20 saniyelik klip
- Proje planı: ≥5 oyuncu, 24 ayrı kayıt

---

## 2. Adım 1 — COCO etiketlemesi

```powershell
.\.venv\Scripts\python.exe -m tennis_tracking.labeler datasets\wall\train
```

| Tuş | İşlev |
|---|---|
| `B` | Top kategorisini seç |
| `R` | Raket kategorisini seç |
| `N` | Kaydet ve sonraki kare |
| `Backspace` | Son kutuyu sil |

- Nesnenin çevresine kutu çiz. **Görünmeyen topu tahmin etme.**
- Kutusuz kaydetmek **negatif örnek** olur; yanlış pozitifleri bastırmak için şart.
- Araç kapanınca **ilk etiketlenmemiş kareden devam eder**; ilerleme kaybolmaz.
- Hedef: **en az 1.500 etiketli kare** (proje dokümanı 1.500–3.000).

### Zaman tahmini (iyimser değil)
| Senaryo | Süre |
|---|---|
| Deneyimli, top net | ~5 s/kare |
| Yeni başlayan, küçük top, büyütme gerekli | ~10–12 s/kare |
| **Gerçekçi toplam (914 kare)** | **2–4 saat**, 2–4 oturuma bölünmeli |

> ⚠️ Not: 2 fps'te çıkarılan ardışık kareler birbirine benzerdir. Bağımsız örnek
> sayısı gerçekte daha düşüktür. Yeni kayıtlarda `--hz 4` kullanılabilir; çeşitlilik
> asıl kaynaktır.

---

## 3. Adım 2 — Manuel olay referansı (F1'in kaynağı)

Kutu etiketlemesi **yalnızca RF-DETR'i eğitir**. Temas F1'i için ayrıca
**olay referansı** gerekir: raket temas anı, duvar temas anı, vuruş tipi (FH/BH),
duvar konumu — en az **100 vuruş** üzerinde, tercihen iki kişi bağımsız
etiketleyip uyuşmazlıkları birlikte çözer.

Bu referans **uygulama içinde** üretilir:

1. Videoyu analiz et → sistem `automatic_shots` tutar (ilk otomatik çıktının kopyası).
2. **Vuruş inceleme** sekmesinde her satırı düzelt: zaman, tip, duvar noktası.
3. Kaçan vuruşları **"Yeni vuruş"** ile elle ekle.
4. Her satırda **"İncelendi · kaydet"** → `reviewed=true`.
5. Yanlış adayları **"Dahil et / çıkar"** ile işaretle (bu, ölçümü bozar).

`evaluate.py` yalnızca tamamı incelenmiş referansı kabul eder:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py data\<OTURUM_KIMLIGI>\session.json --output data\degerlendirme.json
```

Çıktılar: `racket_contacts` / `wall_contacts` (precision, recall, F1),
`classification_coverage`, `classification_accuracy`,
`placement_mean_normalized_error`, `speed_validated` (her zaman false).

### İki kişilik etiketleme
- Bir kişi vuruşları işaretler, ikinci kişi bağımsız kontrol eder.
- Uyuşmazlıklar birlikte çözülür ve karar `PROGRESS.md`'ye not edilir.

---

## 4. Adım 3 — GPU ortamı

```powershell
Compress-Archive -Path datasets\wall\train\*.jpg, datasets\wall\train\_annotations.coco.json -DestinationPath train.zip
Compress-Archive -Path datasets\wall\test\*.jpg,  datasets\wall\test\_annotations.coco.json  -DestinationPath test.zip
```

Colab: **Runtime → T4 GPU** → zip'leri yükle → `scripts/train_detector.py` dosyasını
`scripts/` klasörüne yükle → eğit.

Ayrıntılı adımlar: [COLAB_TRAINING.md](COLAB_TRAINING.md)

### Kritik uyarılar
| Uyarı | Açıklama |
|---|---|
| **Checkpoint'leri Drive'a kaydet** | Colab oturumları kesilir; `runs/` klasörü kaybolur. Eğitim sırasında Drive'a kopyala. |
| **Klasör yapısını doğrula** | `Compress-Archive` Linux'ta yolu bozabilir. Açtıktan sonra `ls datasets/wall/train | head` ile `_annotations.coco.json` dosyasının **yan yana** olduğunu kontrol et. |
| **Sürüm yedeği** | `rfdetr==1.11.0` PyPI'da mevcut. Kurulum yine de sorun verirse numarasız `pip install rfdetr` ile en son sürüme geç ve `models/README.md`'deki `rfdetr_version` alanını güncelle. |
| **test'e dokunma** | Eşikler `valid` üzerinde ayarlanır. `test` **yalnızca bir kez**, son ölçüm için kullanılır. |

---

## 5. Adım 4 — Karşılaştırma deneyi

Proje planı: "HSV taban çizgisi ve ince ayarlı RF-DETR" karşılaştırması.

| Deney | Veri | Ölçüm |
|---|---|---|
| E1 — HSV taban çizgi | test kaydı, renk modu | F1, sınıflandırma kapsamı/doğruluğu |
| E2 — RF-DETR | aynı test kaydı, RF-DETR modu | aynı metrikler |
| E3 — Ses açık/kapalı | aynı sabit test kümesi | ses ipucunun katkısı |
| E4 — Çoklu oyuncu | kendi kayıtlarımız | genellenebilirlik |

> E1–E3 aynı **sabit** test kümesinde yapılır.

---

## 6. Adım 5 — Deney kaydı

`docs/TEST_RAPORU.md` içine her koşu için:

| Tarih | Ortam | Veri | Epoch | F1 | Sınıflandırma | Not |
|---|---|---|---|---|---|---|
| | Colab T4 / Kaggle | train 914 / test 166 | 40 | | | |

`PROGRESS.md` dosyasında **günlük** ilerleme: kaç kare etiketlendi, kaç vuruş
referanslandı, kaç saat sürdü, neye takıldı.

---

## 7. Bu hafta hedef

| Gün | İş | Çıktı |
|---|---|---|
| 1 | Etiketlemeye başla (train) + Colab hesabı aç | 150+ kare |
| 2 | Etiketleme devam + **test** etiketlemesi | 400+ kare |
| 3 | Etiketleme + **valid kaydı çekimi planı** | 700+ kare |
| 4 | Etiketleme tamamla + **manuel olay referansı** başla | 914+166 kare |
| 5 | İlk RF-DETR eğitimi (Colab) | `wall-nano.pth` |
| 6 | Modeli teste uygula + `evaluate.py` + E1/E2 karşılaştırması | **ilk F1** |
| 7 | `TEST_RAPORU` + `PROGRESS.md` + sunum tekrarı | hazır |

---

## 8. Tez notu — donanım

Donanım kapsam dışıdır. Ağırlık **hiçbir yerde** donanım doğrulaması iddiası
bulunmaz. "Gelecek çalışma" başlığı altında tek cümle yeterlidir:

> "ESP32 + OLED sonuç ekranı için protokol ve kart yazılımı tasarlanmış ve
> yazılım düzeyinde test edilmiştir; fiziksel entegrasyon kapsam dışı bırakılmıştır."
