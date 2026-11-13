# Kendi duvarına uygun model

Uygulamanın varsayılanı renk/hareket takibidir. Genel MediaPipe modeli vücudu izler.

> ✅ **13 Kasım 2026:** Bu depodaki veri setiyle eğitilmiş **RF-DETR Nano**
> ağırlıkları artık mevcut: `models/wall-nano.pth` + `models/wall-nano.json`
> (40 epoch, train 734 / valid 180 kare, çözünürlük 576).
> Ayrıntı ve ölçüm sonuçları: [TEST_RAPORU.md](TEST_RAPORU.md).
> Model tanımı ve kurulum: [models/README.md](../models/README.md).

## 1. Ayrı çekimleri bölümlere ayır

En az üç ayrı çekim oturumu kullan. Aynı antrenmanın benzer kliplerini aynı bölümde tut. Test kliplerini eşik seçmek veya modeli geliştirmek için kullanma. Başlangıç olarak görüntülerin yaklaşık %70'i eğitim, %15'i doğrulama, %15'i test olabilir; ayrımı kare değil oturum düzeyinde yap.

```powershell
.\.venv\Scripts\python.exe scripts/extract_frames.py C:\videolar\gun1.mp4 --split train
.\.venv\Scripts\python.exe scripts/extract_frames.py C:\videolar\gun2.mp4 --split valid
.\.venv\Scripts\python.exe scripts/extract_frames.py C:\videolar\gun3.mp4 --split test
```

Varsayılan saniyede 2 kare. Dosya içeriğinin hash'i adlara eklenir; aynı video başka bölüme tekrar alınamaz. Farklı dosyalara bölünmüş aynı çekimi sistem otomatik tanıyamaz; onları aynı bölümde tut.

**Klib bazlı bölme:** `scripts/split_pilot.py` yalnızca bütün klipleri taşır ve
aynı çekimin iki bölümde birden bulunmasını reddeder.

```powershell
.\.venv\Scripts\python.exe scripts\split_pilot.py --dataset datasets\wall --valid-clips 3 --dry-run
```

## 2. Yerel kutu etiketleyici

```powershell
.\.venv\Scripts\python.exe -m tennis_tracking.labeler datasets/wall/train
.\.venv\Scripts\python.exe -m tennis_tracking.labeler datasets/wall/valid
.\.venv\Scripts\python.exe -m tennis_tracking.labeler datasets/wall/test
```

Top için B, raket için R; nesnenin çevresine sürükleyerek kutu çiz. N kaydedip sonraki kareye geçer. Backspace son kutuyu siler. Görünmeyen topu tahmin etme. Kutusuz kaydetmek negatif örnektir. Kapanırken mevcut kare kaydedilir. Yalnızca incelenip kaydedilen kareler COCO listesine alınır.

Kategoriler sabittir: `0=ball`, `1=racket`. Her bölümde görüntüler ve `_annotations.coco.json` bulunur. Arka plandaki top benzeri lekeler negatif örneklerle temsil edilmeli. Bulanık top ve farklı raket yönleri de etiketlenmeli.

Kontrol:

```powershell
.\.venv\Scripts\python.exe scripts/train_detector.py --dataset datasets/wall --check-only
```

## 3. GPU üzerinde eğitim

Bu bilgisayarda AMD Vega 8 bulunuyor; CUDA eğitim hedefi değil. `notebooks/train_wall.ipynb` CUDA GPU bulunan bir notebook ortamı içindir. Veri setini ve `scripts/train_detector.py` dosyasını seçtiğin ortama kendin aktar; uygulama bunu otomatik yüklemez. Ücretli hizmete abonelik veya harcama yapılmadı.

Notebook, `rfdetr==1.11.0` ile Nano modelini 560 piksel çözünürlükte, 40 epok üst sınırı ve erken durdurmayla uyarlar. Varsayılan ön eğitim ağırlıkları ilk çalıştırmada indirilir. Eğitim sonrasında `wall-nano.pth` ve `wall-nano.json` paketini al.

Uygulama ortamına RF-DETR eklemek için:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ai]"
```

Model ve JSON tanımını aynı klasöre koy; uygulamada **RF-DETR modeli seç** ile `.pth` dosyasını aç. Mimari, sınıf kimlikleri, çözünürlük ve model SHA256 özeti JSON'dan okunur. Modelin test videolarındaki yeterliliği ayrıca ölçülür; varsayılan COCO spor topu sınıfı özel tenis modeli yerine sunulmaz.

## 4. Gerçek başarıyı ölç

Test videosunu otomatik analiz et. İnceleme sekmesinde bütün gerçek vuruşları kaydet: yanlış adayları hariç bırak, kaçanları elle ekle, bütün dahil edilmiş vuruşları incelendi olarak kaydet. Raket/duvar zamanı ve forehand/backhand referanslarını video üzerinden kontrol et. Mümkünse ikinci kişi etiketleri denetlesin.

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py data\OTURUM_KIMLIGI\session.json --output data\degerlendirme.json
```

İlk otomatik çıktı, sonradan düzeltilmiş referansla eşleştirilir. Varsayılan zaman toleransı ±80 ms; bu gevşek tolerans 60 FPS hız doğruluğu kanıtı değildir. Temas precision/recall/F1, sınıflandırma kapsaması/doğruluğu ve normalize duvar hatası ayrı raporlanır. Yanlış adayları referansa dahil bırakmak ölçümü bozar. Sentetik arayüz örneği değerlendirmeye kabul edilmez.

Başlangıç kabul hedefleri: en az 100 gerçek test vuruşu; temas F1 ≥ %90; sınıflandırma kapsaması ≥ %80 ve sınıflandırılanlarda doğruluk ≥ %90. Henüz bu değerler ölçülmedi. Hızın doğrulanması ayrıca bağımsız zaman/mesafe veya radar referansı gerektirir; değerlendirme aracı `speed_validated:false` döndürür.
