# RF-DETR pilot eğitim — tek komut

Bu dosya pilot eğitimin son adımını yapar: etiketlenmiş kareleri sıkıştırır,
Colab'a yüklenecek arşivleri üretir ve kontrol eder.

## Ne zaman çalıştırılır

1. `Baslat.cmd` ile uygulamayı aç.
2. **Veri etiketleme** penceresinde kareleri etiketle:
   - `B` → top kategorisi, `R` → raket kategorisi
   - `N` → kaydet ve sonraki kare, `Backspace` → son kutuyu sil
   - Pencereyi kapatınca **ilk etiketlenmemiş kareden devam eder**.
3. Bu dosyaya çift tıkla.
4. Oluşan `train.zip` ve `valid.zip` dosyalarını Colab'a yükle.

## Çıktılar

- `train.zip` — eğitim kareleri + `_annotations.coco.json` (kök dizinde)
- `valid.zip` — doğrulama kareleri + `_annotations.coco.json` (kök dizinde)

`test` bölümü bilerek paketlenmez: eşik ayarı `valid` üzerinde yapılır,
`test` yalnızca son ölçüm için saklanır.

## Colab'da

1. `train_colab.ipynb` dosyasını Colab'a yükle.
2. **Runtime → Change runtime type → T4 GPU**.
3. `train.zip` ve `valid.zip` dosyalarını yükle.
4. **Run all**.

Ayrıntılar: [docs/COLAB_TRAINING.md](docs/COLAB_TRAINING.md)
