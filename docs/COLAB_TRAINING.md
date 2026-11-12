# RF-DETR eğitimi — GPU'suz ortamda (Google Colab / Kaggle)

Bu bilgisayarda AMD Vega 8 var; CUDA destekliyor mu kontrol edilmedi. RF-DETR
Nano eğitimi CUDA gerektirir. Bu belge, veri setini hazırlayıp GPU'lu bir
ortamda eğitmeyi adım adım anlatır.

## 0. Durum (12 Kasım 2026)

| Adım | Durum |
|---|---|
| Veri kareleri çıkarıldı | ✔ `datasets/wall/train` (960 kare), `datasets/wall/test` (166 kare) |
| COCO etiketlemesi | ✘ **Bekliyor — kritik yol** |
| GPU ortamı | ✘ Bekliyor (Colab / Kaggle / üniversite laboratuvarı) |
| Eğitim scripti hazır | ✔ `scripts/train_detector.py` (40 epoch, batch 2, lr 1e-4, erken durdurma 8) |
| Notebook hazır | ✔ `notebooks/train_wall.ipynb` |

## 1. Etiketleme (en uzun adım, kendi bilgisayarında)

```powershell
.\.venv\Scripts\python.exe -m tennis_tracking.labeler datasets\wall\train
```

- Top için `B`, raket için `R` seç; nesnenin çevresine kutu çiz.
- `N` = kaydet ve sonraki kare, `Backspace` = son kutuyu sil.
- **Görünmeyen topu tahmin etme.** Kutusuz kaydetmek negatif örnek olur ve modele
  yardımcıdır (yanlış pozitifleri bastırmak için).
- Araç kapandığında **ilk etiketlenmemiş kareden devam eder**; ilerleme kaybolmaz.
- Hedef: **en az 1.500 etiketli kare** (proje dokümanı: 1.500–3.000).

### Bölüm ayrımı kuralı
Aynı çekimin klipleri **tek bölümde** tutulur. Mevcut dağılım:

| Kayıt | Bölüm | Neden |
|---|---|---|
| "How to Train on a Tennis Wall" (16 klip) | **train** | Tek kayıt; tümü aynı bölümde |
| `13134650_1920_1080_30fps.mp4` | **test** | Farklı kayıt, farklı kamera açısı |
| **Kaydedilecek yeni çekim** | **valid** | Üçüncü bağımsız kayıt gerekiyor |

> ⚠️ `extract_frames.py` aynı **dosya** hash'ini iki bölüme koymayı engeller, ama
> aynı kaydın farklı kliplerini (farklı hash) engellemez. Bu yüzden bölümleme
> elle, kayıt seviyesinde yapılmalıdır.

## 2. Veri setini GPU ortamına taşı

**Otomatik yol (önerilen).** `scripts/pack_pilot.py` yalnızca etiketlenmiş kareleri
paketler ve arşivin kök dizinine görselleri + `_annotations.coco.json` dosyasını
koyar. Böylece Colab'da iç içe klasör sorunu oluşmaz.

```powershell
.\.venv\Scripts\python.exe scripts\pack_pilot.py --dataset datasets\wall --output .
# -> train.zip, valid.zip
```

> `Compress-Archive` yerine bu yol kullanılmalı. `Compress-Archive` çıktısı
> Linux'ta yolu bozabiliyor ve etiketlenmemiş kareleri de içine alıyor.

Kaggle kullanıyorsan `datasets/wall` klasörünü olduğu gibi yükle (zip'e gerek yok).

## 3. Colab'da eğitim

**Hazır notebook:** `train_colab.ipynb` (proje kökünde). Dosyayı Colab'a yükle,
**Runtime → Change runtime type → T4 GPU** seç, `train.zip` ve `valid.zip`
dosyalarını yükle, **Run all** çalıştır.

Notebook sırasıyla: Drive bağlantısı → GPU kontrolü → `rfdetr==1.11.0` kurulumu →
`train.zip`/`valid.zip` bulma → arşivleri `/content/wall/{train,valid}` altına
açma → COCO bütünlük ve **çekim sızıntısı** kontrolü → 5 epoch pilot eğitimi →
model paketini (`wall-nano.pth` + `wall-nano.json`) hazırlama → Drive'a kopyalama.

> Notebook'u `scripts/make_colab_notebook.py` üretir. Hücreleri değiştirmek istersen
> scripti düzenleyip yeniden çalıştır; elle JSON düzenleme hatalı not defteri üretir.

Manuel yol:

1. **Runtime → Change runtime type → T4 GPU**
2. `train.zip` ve `valid.zip` dosyalarını Colab'a yükle.
3. Aşağıdaki hücreleri sırayla çalıştır:

```python
!pip install rfdetr==1.11.0

import zipfile, os
os.makedirs("datasets/wall", exist_ok=True)
for name in ("train", "valid"):
    with zipfile.ZipFile(f"{name}.zip") as z:
        z.extractall(f"datasets/wall/{name}")

import torch
print(torch.cuda.is_available(), torch.cuda.get_device_name(0))
```

4. **Klasör yapısını doğrula.** RF-DETR `dataset_dir/{train,valid,test}`
   düzenini bekler ve her bölümde `_annotations.coco.json` arar. Açtıktan sonra
   şunu çalıştır ve dosyanın **resimlerin yan yana** olduğunu gör:

```python
!ls datasets/wall/train | head
!ls datasets/wall/train/_annotations.coco.json
```

   Dosya görünmüyorsa zip'i `scripts/pack_pilot.py` ile yeniden üret.

5. `scripts/train_detector.py` dosyasını Colab'a yükle (`scripts/` klasörüne).
6. Eğitimi başlat:

```python
!python scripts/train_detector.py --dataset datasets/wall --output runs/wall-nano --epochs 40
```

7. `notebooks/train_wall.ipynb` içindeki hücreler aynı işi yapar; hazır senaryo olarak
   kullanılabilir ama dosyaların Colab çalışma klasöründe olduğunu doğrula.

### Checkpoint'leri Google Drive'a kaydet

Colab oturumları kesilir ve `runs/` klasörü kaybolur. Eğitim sırasında
periyodik olarak Drive'a kopyala:

```python
from google.colab import drive
import os, shutil
drive.mount("/content/drive")
shutil.copytree("runs/wall-nano", "/content/drive/MyDrive/wall-nano",
                dirs_exist_ok=True)
```

Eğitim bitince `runs/wall-nano/wall-nano.pth` ve `wall-nano.json` dosyalarını indir.


## 4. Modeli uygulamaya taşı

Çıktıdan alınacak iki dosya:

- `runs/wall-nano/wall-nano.pth`
- `runs/wall-nano/wall-nano.json`

İkisini birlikte `models/` klasörüne kopyala ve uygulamada
**Ölçüm/takip → RF-DETR modeli seç** ile `.pth` dosyasını seç.

`models/README.md` içindeki şablon şu alanları içermeli:

```json
{
  "architecture": "RFDETRNano",
  "resolution": 560,
  "class_ids": {"ball": 0, "racket": 1},
  "rfdetr_version": "1.11.0",
  "sha256": "<EĞİTİM_ARACININ_ÜRETTİĞİ_GERÇEK_SHA256>"
}
```

## 5. Değerlendirme (eğitimden sonra)

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py data\<OTURUM_KIMLIGI>\session.json --output data\degerlendirme.json
```

Değerlendirme otomatik çıktıyı **elle incelenmiş referansla** karşılaştırır.
Referansın tamamı `reviewed` olmalıdır. `speed_validated` her zaman `false` kalır.

## 6. Deney kaydı tutulacak

`docs/TEST_RAPORU.md` içine her koşu için:

| Tarih | Ortam | Veri | Epoch | Sonuç | Not |
|---|---|---|---|---|---|
| | Colab T4 / Kaggle TPU | train 960 / test 166 | | | |

Ayrıca `PROGRESS.md` dosyasında günlük ilerleme (kaç kare etiketlendi, kaç saat
sürdü) tutulmalıdır. Tezde "tekrarlanabilir deney" maddesi bunu ister.
