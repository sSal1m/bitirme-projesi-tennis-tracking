# Modeller

`scripts/download_pose.py`, Google'ın resmi MediaPipe Pose Landmarker Lite float16/1 dosyasını indirir. Çalışan dosya `pose_landmarker_lite.task`; yanında yerel SHA256 kaydı bulunur. Kaynak: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker

Tenis topu/raketi için bu depoda eğitilmiş ağırlık yok. RF-DETR Nano eğitiminden sonra `wall-nano.pth` ve aynı adlı `wall-nano.json` kullanılır. Model tanımı:

```json
{
  "architecture": "RFDETRNano",
  "resolution": 560,
  "class_ids": {"ball": 0, "racket": 1},
  "rfdetr_version": "1.11.0",
  "sha256": "EĞİTİM_ARACININ_ÜRETTİĞİ_GERÇEK_SHA256"
}
```

Bu şablon bir model değildir. Ağırlık ile JSON eşleşmiyorsa uygulama modeli yüklemez. İndirilen dosyalar Git dışında tutulur. Kullanım ve eğitim için `docs/MODEL_EGITIMI.md` dosyasını izle.
