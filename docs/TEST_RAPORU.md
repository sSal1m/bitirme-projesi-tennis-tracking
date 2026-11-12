# Doğrulama kaydı — 29 Eylül 2026

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
