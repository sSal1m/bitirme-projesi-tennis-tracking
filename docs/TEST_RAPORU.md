# Doğrulama kaydı — 29 Eylül 2026

## Doğrulama kaydı — 13 Kasım 2026

### RF-DETR Nano eğitimi ve model doğrulaması

**Eğitim:** Google Colab (T4 GPU), `rfdetr==1.11.0`, 40 epoch, `train` 734 kare /
`valid` 180 kare, çözünürlük 576. Çıktı `wall-nano.pth` + `wall-nano.json`
(`models/` klasörüne yerleştirildi).

**Model bütünlüğü:**

| Kontrol | Sonuç |
|---|---|
| `wall-nano.json` içindeki SHA256 ile `wall-nano.pth` özeti | ✔ **aynı** (`63ddb47b…900d9f`) |
| Mimari / sınıf eşlemesi | ✔ `RFDETRNano`, `ball=0`, `racket=1` |
| Çözünürlük uygunluğu | ✔ 576 = 32 × 18 (`patch_size 16 × num_windows 2`) |
| Checkpoint yapısı | ✔ 477 tensor, 116.3 MB, PyTorch arşivi geçerli |
| Uygulama yükleyicisi | ✔ `RFDETRDetector` modeli 5.2 sn'de yükledi |
| Çıkarım hızı (CPU) | ✔ ~0.20 sn/kare |

### Kutü tespiti: RF-DETR vs HSV (elle etiketlenmiş `valid` bölümü)

Referans: 178 karenin elle çizilmiş `ball` ve `racket` kutuları. Her iki dedektör
**aynı karelerde, aynı referansa** karşı çalıştırıldı.

| Sınıf | Yöntem | TP | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|---|
| ball | RF-DETR | 32 | 124 | 97 | 20.5% | 24.8% | 22.5% |
| ball | HSV | 0 | 301 | 129 | 0.0% | 0.0% | 0.0% |
| racket | RF-DETR | 140 | 30 | 15 | 82.4% | 90.3% | 86.2% |
| racket | HSV | 0 | 0 | 155 | 0.0% | 0.0% | 0.0% |

**Toplam (iki sınıf):** RF-DETR P=52.8% R=60.6% F1=**56.4%** · HSV F1=**0.0%**

#### Küçük nesne düzeltmesi

Top referans kutuları kare alanının medyan **%0.09**'u (en küçük %0.016) — yani
birkaç piksel genişliğinde. Bu kutular için IoU oranı, modelin kutusunun
referanstan birkaç piksel farklı olmasıyla bile çöker. Bu yüzden ikinci bir
ölçüt de raporlandı: **tahmin merkezinin referans kutusunun içinde olması**.

| Sınıf | Yöntem | P | R | F1 |
|---|---|---|---|---|
| ball | RF-DETR | 79.5% | 96.1% | **87.0%** |
| ball | HSV | 40.2% | 93.8% | 56.3% |
| racket | RF-DETR | 91.2% | 100.0% | **95.4%** |
| racket | HSV | 0.0% | 0.0% | 0.0% |
| **toplam** | **RF-DETR** | **85.6%** | **98.2%** | **91.5%** |
| **toplam** | **HSV** | 40.2% | 42.6% | 41.4% |

RF-DETR'in top tahminlerinin **%99.2**'si doğru topun üzerine düşüyor; IoU'yu
düşüren tek şey kutu boyutundaki fark. HSV ise çok daha fazla yanlış pozitif
üretiyor (276 top tahmini).

Raplayıcı: `scripts/compare_detectors.py` → `data/rfdetr_vs_hsv.json`

### Uçtan uca uygulama doğrulaması

`clip_09_0269-0299.mp4` **aynı kalibrasyonla** iki kez analiz edildi:

| | HSV (renk/hareket) | RF-DETR (wall-nano) |
|---|---|---|
| Vuruş adayı | 13 | **32** |
| Duvar teması bulunan | 12 | 31 |
| Konum bulunan | 12 | 31 |
| forehand / backhand / belirsiz | 2 / 7 / 4 | **17 / 11 / 4** |
| Ortalama güven | 0.564 | **0.729** |
| Uyarı sayısı | 2 | 1 |

±0.3 sn eşleştirmesinde **HSV'nin 13 adayının 13'ü de RF-DETR tarafından
bulundu** (yalnız HSV: 0). RF-DETR 19 aday daha üretti; bunların gerçek vuruş
olup olmadığı **elle inceleme ile** belirlenmelidir.

Ayrıca uygulamaya `--session` seçeneği eklendi: bir oturum doğrudan inceleme
sekmesinde açılabiliyor.

```powershell
.\.venv\Scripts\python.exe -m tennis_tracking.app --session d1e747d3c39b402994afc54f077d5c1d
```

### Bekleyen doğrulamalar

- **Vuruş F1'i ölçülmedi.** `scripts/evaluate.py` elle incelenmiş bir referans
  ister; 32 adayın hangilerinin gerçek vuruş olduğu henüz incelenmedi.
- `valid` bölümü **aynı kayıttan** geldiği için genellenebilirlik kanıtı
  değildir; üçüncü bağımsız kayıt hâlâ eksik.
- `test` bölümünün (166 kare, farklı kayıt) etiketleri yok; gerçek tutulmuş
  ölçüm için etiketlenmeli.

## Doğrulama kaydı — 12 Kasım 2026

### Donanım yazılımı derlemesi

- PlatformIO 6.2.0 kuruldu; `espressif32@6.10.0` ve `esp32dev` hedefi ile
  `.\.venv\Scripts\python.exe -m platformio run -d firmware` **başarıyla tamamlandı**.
- Çıktı: `firmware/.pio/build/esp32dev/firmware.bin` ve `firmware.elf`.
- Kaynak kullanımı: RAM %6.7 (22.016 / 327.680 bayt), Flash %23.4 (307.273 / 1.310.720 bayt).
- Eylül ayındaki ArduinoJson 7 proxy hatası mevcut kaynakta zaten giderilmiş durumda;
  `JsonObjectConst` okuması derlendi. **Kart yazılımı artık derleme açısından doğrulanmıştır.**
- Derleme süresi ilk kurulumda yaklaşık 14 dakika sürdü (araç zinciri indirmesi dahil).

### Bilgisayar tarafı protokol sözleşmesi

- `tests/test_hardware_protocol.py` eklendi: `firmware/src/main.cpp` içindeki
  `receiveLine()` doğrulama mantığının Python karşılığı. Kart bağlanmadan önce
  özet paketinin kart tarafından kabul edileceğini kanıtlar.
- Kapsanan durumlar: sürüm, sayaç tutarlılığı (FH+BH+belirsiz=toplam), reviewed ve
  localized sınırları, isabet oranı aralığı (0-100), negatif hız, eksik alan, bozuk satır.
- Toplam test sayısı 74'e çıktı (64 + 10), Ruff denetimi temiz.

### Gerçek video ile yapılan saha ölçümü

- Üç video adayı sisteme yüklendi ve ölçüldü:
  - 480p, oyuncu kadrajda yok: **0 vuruş adayı**, reddedildi.
  - 1080p, kamera eğik: 41 aday, yalnızca 13'ünde duvar konumu bulundu, güvenilmez.
  - 1080p/24fps, sahne değişimi var: bölünmeden önce 189 aday ancak **0 duvar konumu**.
- Sahne değişimleri `scripts/split_video.py` ile tespit edilip 30 saniyelik kliplere
  bölündü (ses korunarak). Kliplerden birinde: top tespiti **%92,2**, 13 vuruş adayı,
  **12'sinde duvar konumu (%92)**, ortalama yaklaşma hızı 30,4 km/sa.
- **Not:** Bu değerler tek bir klibin ölçümüdür, saha başarı iddiası değildir.
  Tam incelenmiş referans, oturum düzeyinde ayrım ve 100+ vuruşluk test kümesi hâlâ eksiktir.

## Yapılan yazılım kontrolleri

- Windows, Python 3.11.9: sanal ortam ve uygulama bağımlılıkları kuruldu; `pip check` temiz.
- Pytest tam paketi: **38 test geçti**. Bu çalıştırmadan sonra eklenen stereo ses ve telefon dönüklüğü dahil hedefli 12 ve 11 testlik çalıştırmalar da geçti. Son ekrandaki değişiklikler bu hedefli çalıştırmada kapsandı.
- Ruff denetimi ve Python bytecode derlemesi temiz.
- Sentetik örnekle uygulama açıldı, ekran görüntüsü incelendi; video, temel kartlar ve grafikler görüntülendi. Bu örnek gerçek saha verisi değildir.
- Gerçek resmi MediaPipe Lite modeli indirildi, SHA256 kontrol edildi ve boş kare testiyle yüklendi.
- Sentetik MP4'ün içe alınması, değişken kare zamanları, döndürülmüş önizleme, stereo ses, elle düzeltme, geçmiş ve işaretlenmiş MP4 çıktısı sınandı.
- Veri etiketleyicisinin COCO çıktısı ve aynı videonun train/valid/test bölümlerine dağılmasının reddi test edildi.

## Bekleyen doğrulamalar

- Kullanıcıya ait tenis duvarı videosu olmadığı için otomatik vuruş sayısı, tür, hedef isabeti veya yaklaşma hızı için saha başarısı ölçülmedi.
- RF-DETR Nano modeli kullanıcının görüntüleriyle henüz eğitilmedi; isteğe bağlı model bağımlılığı mevcut temel ortama kurulmadı.
- Bağlı ESP32/OLED/COM portu bulunmadı. Kullanıcının isteğiyle donanım testleri şimdilik durduruldu.
- İlk PlatformIO derleme denemesi ArduinoJson 7 proxy karşılaştırmasında hata verdi. Kaynak, sabit `JsonObjectConst` okumasına çevrildi. **12 Kasım 2026'da derleme tekrar çalıştırıldı ve başarılı oldu** (bkz. yukarıdaki kayıt). Kart yazılımının **fiziksel çalışması ve ekran testi hâlâ doğrulanmamıştır.**

## Saha kabulü için uygulanacak deney

1. Farklı gün ve ışıklarda, kalibrasyonu kaydedilmiş en az üç gerçek çekim oturumu topla.
2. Test oturumunda en az 100 vuruşu videodan elle işaretle ve referansı bağımsız gözden geçir.
3. Eğitim/test ayrımı oturum düzeyinde olsun; test videolarını eşik ayarı için kullanma.
4. `scripts/evaluate.py` ile raket ve duvar teması F1, sınıflandırma kapsaması/doğruluğu ve isabet konumu hatasını raporla.
5. Hız doğruluğu için bağımsız referans yoksa başarı iddiasında bulunma; sonuç yalnızca yaklaşma hızı tahmini olarak kalır.
6. Donanım testleri tekrar kapsamdayken `docs/DONANIM.md` içindeki fiziksel kontrol adımlarını uygula.
