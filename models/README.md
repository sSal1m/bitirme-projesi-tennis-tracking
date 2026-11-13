# Modeller

`scripts/download_pose.py`, Google'ın resmi MediaPipe Pose Landmarker Lite float16/1 dosyasını indirir. Çalışan dosya `pose_landmarker_lite.task`; yanında yerel SHA256 kaydı bulunur. Kaynak: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker

## wall-nano — eğitilmiş RF-DETR Nano

`wall-nano.pth` ve `wall-nano.json`, **bu depodaki kendi veri setiyle** eğitilmiş
top/raket dedektörüdür. Uygulama bu ağırlığı tanır:

| Alan | Değer |
|---|---|
| Mimarî | `RFDETRNano` |
| Çözünürlük | 576 |
| Sınıflar | `ball` = 0, `racket` = 1 |
| rfdetr sürümü | 1.11.0 |
| Eğitim | 40 epoch, train 734 / valid 180 kare |
| SHA256 | `63ddb47bec53f12058e067e5b1468424020b477564b3a46a67c77f58d8900d9f` |

**Doğrulama.** `wall-nano.json` içindeki `sha256` ile `wall-nano.pth` dosyasının
gerçek özeti eşleşmelidir; eşleşmezse uygulama modeli yüklemez
(`RFDETRDetector` sırasında `ValueError` fırlatır).

```powershell
(Get-FileHash models\wall-nano.pth -Algorithm SHA256).Hash.ToLower()
```

Ağırlık `models/` altında yerelde kalır; Git'e yazılmaz.

### Kullanım

Uygulamada **Ölçüm/takip → RF-DETR modeli seç** ile `models/wall-nano.pth`
dosyasını seç, ardından **Antrenmanı analiz et**. Renk (HSV) modu model
dosyası olmadan da çalışır.

### Kurulum bağımlılıkları

RF-DETR çıkarımı `torch` gerektirir:

```powershell
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
.\.venv\Scripts\python.exe -m pip install -e ".[ai]"
```

`rfdetr` paketi `data/vendor/rfdetr-1.11.0-py3-none-any.whl` içinde saklanır;
internet olmayan kurulumda `--no-index --find-links=data/vendor` kullanılabilir.

## Şablon (başka bir model eğitirsen)

```json
{
  "architecture": "RFDETRNano",
  "resolution": 560,
  "class_ids": {"ball": 0, "racket": 1},
  "rfdetr_version": "1.11.0",
  "sha256": "EĞİTİM ARACININ ÜRETTİĞİ GERÇEK SHA256"
}
```

Bu şablon bir model değildir. Ağırlık ile JSON eşleşmiyorsa uygulama modeli
yüklemez. Kullanım ve eğitim için `docs/MODEL_EGITIMI.md` dosyasını izle.
