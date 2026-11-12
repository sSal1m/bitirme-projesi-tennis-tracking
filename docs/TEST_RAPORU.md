# Doğrulama kaydı — 29 Eylül 2026

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
- İlk PlatformIO derleme denemesi ArduinoJson 7 proxy karşılaştırmasında hata verdi. Kaynak, sabit `JsonObjectConst` okumasına çevrildi; kullanıcının isteğine uyarak derleme tekrar çalıştırılmadı. **Kart yazılımı şu anda derleme ve fiziksel çalışma bakımından doğrulanmış sayılmaz.**

## Saha kabulü için uygulanacak deney

1. Farklı gün ve ışıklarda, kalibrasyonu kaydedilmiş en az üç gerçek çekim oturumu topla.
2. Test oturumunda en az 100 vuruşu videodan elle işaretle ve referansı bağımsız gözden geçir.
3. Eğitim/test ayrımı oturum düzeyinde olsun; test videolarını eşik ayarı için kullanma.
4. `scripts/evaluate.py` ile raket ve duvar teması F1, sınıflandırma kapsaması/doğruluğu ve isabet konumu hatasını raporla.
5. Hız doğruluğu için bağımsız referans yoksa başarı iddiasında bulunma; sonuç yalnızca yaklaşma hızı tahmini olarak kalır.
6. Donanım testleri tekrar kapsamdayken `docs/DONANIM.md` içindeki fiziksel kontrol adımlarını uygula.
