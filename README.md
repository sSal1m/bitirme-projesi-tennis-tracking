# Duvar / Tenis

Telefon videosundan duvar antrenmanı inceleyen, Windows üzerinde yerel çalışan bir ders projesi prototipi. Video yükleme, dört noktalı duvar kalibrasyonu, top ve vücut takibi, vuruş inceleme, hedef isabeti, geçmiş ve ESP32 OLED sonuç ekranı içerir.

## Başlat

Bu bilgisayarda sanal ortam hazırlandı. **`Baslat.cmd` dosyasına çift tıkla.** Yeni kurulumda Python 3.11 kurulu olmalı; önce `Kurulum.cmd`, sonra `Baslat.cmd` çalıştırılır. İlk kurulum internet gerektirir; analiz videoları bir sunucuya göndermez.

Terminalden:

```powershell
.\.venv\Scripts\python.exe -m tennis_tracking.app
```

Arayüzü denemek için **Örnek oturumu keşfet** düğmesi var. Bu video ve etiketleri sentetiktir; analiz doğruluğunun kanıtı değildir.

## Çalışan özellikler

- MP4/MOV/MKV/AVI yükleme, oynatma ve temas anlarını inceleme.
- Perspektifli duvarı dört köşeden işaretleme, hedef alanını haritada sürükleyerek seçme.
- CPU üzerinde deneysel sarı/yeşil top takibi; MediaPipe Lite ile vücut iskeleti.
- Kanıtı yeterli görüntü dönüşlerinden raket–duvar temas adayları ve sağ/sol ele göre forehand/backhand tahmini.
- Vuruş ekleme, zamanı/türü/duvar noktasını düzeltme, hatalı adayı istatistiklerden çıkarma.
- İlk otomatik çıktıyı değiştirmeden ayrı saklama; yerel SQLite geçmişi ve JSON kayıtları.
- Antrenman geçmişinde kaydı seçip **Seçili antrenmanı sil** ile analiz kaydını kaldırma; kaynak video dosyası korunur.
- Hedef isabet yüzdesi, duvar haritası, ölçümlü düzenekte yaklaşma hızı tahmini.
- CSV/JSON ve **sessiz** işaretlenmiş MP4 dışa aktarma.
- ESP32'ye USB üzerinden özet gönderme ve karttan alındı yanıtını kontrol etme.
- Çekim bazında veri hazırlama, yerel kutu etiketleyici, RF-DETR eğitim aracı ve değerlendirme aracı.
- RF-DETR pilot boru hattı: klib bazlı bölme, Colab'a hazır arşiv, tek tikla eğitim notebook'u.

## RF-DETR pilot eğitimi (Colab)

Model eğitimi için etiketleme, bölme, paketleme ve Colab adımları:
**[PILOT_EGITIM.md](PILOT_EGITIM.md)** ve [docs/COLAB_TRAINING.md](docs/COLAB_TRAINING.md).

Kısa özet:

```powershell
# 1) Bölme (yalnızca bütün klipler taşınır, sızıntı olmaz)
.\.venv\Scripts\python.exe scripts\split_pilot.py --dataset datasets\wall --valid-clips 3 --dry-run

# 2) Etiketleme (iki pencere: valid ve train)
.\.venv\Scripts\python.exe -m tennis_tracking.labeler datasets\wall\valid
.\.venv\Scripts\python.exe -m tennis_tracking.labeler datasets\wall\train

# 3) Paketleme -> train.zip + valid.zip  (veya PilotPaketle.cmd)
.\.venv\Scripts\python.exe scripts\pack_pilot.py --dataset datasets\wall --output .
```

Ardından `train_colab.ipynb` dosyasını Colab'da **T4 GPU** ile aç, `train.zip`
ve `valid.zip` dosyalarını yükle ve **Run all** çalıştır.

## Gerçek çekimde ilk kullanım

1. Telefonu sabitle; arka kamerayla normal hızda 1080p/60 FPS çek. Oyuncunun tamamı, raket ve duvar aynı karede olsun. Başlangıçta 20–30 saniyelik klipler kullan.
2. **Video yükle** ile dosyayı seç. Raket elini belirt. Yalnızca gerçekten aynalanmış kayıt için aynalama seçeneğini aç.
3. **Duvarın 4 köşesini seç**: düzlem üzerinde gerçek bir dikdörtgenin sol üst, sağ üst, sağ alt ve sol alt köşelerine tıkla. Çapraz sıralama geçersizdir.
4. Alt haritada sürükleyerek hedefi seç. Renk/hareket modu ilk deneme içindir. **Antrenmanı analiz et** düğmesine bas.
5. **Vuruş inceleme** sekmesinde adayları kontrol et. Satıra çift tıklamak videoyu ilgili ana götürür. Gerekirse yeni vuruş ekle; duvar zamanını gir, **Duvardaki noktayı seç** ile topun duvara temas ettiği noktaya tıkla ve **İncelendi · kaydet** kullan.
6. Hız istiyorsan duvardan topun rakete temas ettiği düzleme dik mesafeyi metre olarak gir. Vuruş boyunca bu mesafenin sabit olduğunu doğrulayan kutuyu işaretle; temasları kontrol edip kaydet. Oyuncunun ayaklarının mesafesi her zaman topun temas mesafesi değildir.
7. Dışa aktar menüsünden istediğin çıktıyı kaydet. Donanım sekmesi takılı ESP32'ye mevcut oturumun özetini gönderir.

## Ölçümlerin anlamı

**İsabet:** hedef içindeki lokalize temas / bütün lokalize temaslar. Konumu belirlenemeyenler ayrıca gösterilir; paydadan çıkarılır. Raket tarafında aday temas görülüp duvar teması bulunamazsa vuruş sayılır, konum ve hız boş bırakılır. Raket teması görülmeyen vuruşlar otomatik olarak sayılmaz; incelerken elle eklenmelidir.

Kart otomatik noktalar için **tahmini** oranı ve `hedefteki / konumu bulunan` sayısını gösterir. Yeşil hedef alanı hem haritada hem videoda görünür. Haritada yeşil noktalar hedef içini, turuncu noktalar hedef dışını gösterir; boş daireler inceleme bekleyen adaylardır. Noktaya tıklayarak ilgili duvar karesine gidebilirsin. Video altındaki dört küçük gösterge oynatma anına kadar başlayan vuruşları ve duvara ulaşmış topların isabet/hız özetini gösterir; geri sarınca yeniden hesaplanır.

Hafif kamera kayması varsa duvar noktaları ilk kareye hizalanır ve isabet sonucu **yaklaşık** olarak işaretlenir. Büyük kamera hareketinde güvenilir duvar konumu üretilemez; çekimi yeniden kalibre ederek tekrarla.

**Hız:** `3,6 × dik mesafe (m) / (duvar zamanı − raket zamanı)`. Raketle temas ettiğin yaklaşık noktadan duvara olan dik mesafeyi metreyle ölçüp **Temas–duvar** alanına gir; **Temas mesafesi sabit ve ölçüldü** kutusunu işaretle. Mevcut oturumda videoyu yeniden işlemeden hesaplamak için **Ölçülen mesafeyi oturuma uygula** düğmesine bas. Sonuç uçuşun duvara dik ortalama hız bileşenidir; raketten çıkış hızı, üç boyutlu hız veya radar ölçümü değildir. Hız kartındaki ana sayı güvenilir tahminlerin ortalamasıdır; Peak bunların en yükseği, Forehand ve Backhand ise ilgili türdeki güvenilir vuruşların ayrı ortalamalarıdır. Grafik her vuruşa bir yer ayırır: yeşil güvenilir tahmin, turuncu `≈` düşük güvenli zaman eşleşmesinden gelen geçici tahmin, kısa gri çizgi hesaplanamayan hızdır. Duvar zamanı bulunamazsa veya süre geçersizse hız üretilmez; ortalama yalnızca güvenilir tahminleri kullanır. Grafikteki vuruşa tıklayıp inceleme sekmesinde temas zamanlarını düzeltebilirsin. Duvardaki homografi havadaki topa uygulanmaz.

**Vücut:** iskelet ve görüntü düzlemindeki temas tarafı incelenir. Tek kameradan doğrulanmış 3B eklem açısı veya kesin teknik antrenör tavsiyesi üretilmez.

**Otomatik aday:** henüz elle kontrol edilmemiş ölçüm. Tahmini top noktaları gri/boş, gözlenenler sarı renkte gösterilir. Görünmeyen top için yeni temas oluşturulmaz.

## Henüz doğrulanmamış kısımlar

Kullanıcıya ait saha videosu ve etiketlenmiş veri henüz yok. **Duvarına özel eğitilmiş tenis modeli bu depoda bulunmuyor.** Renk modu yeşil zemin, sarı giysi, küçük top, hareket bulanıklığı ve örtülmede hata yapabilir; hiç vuruş bulamayabilir. MediaPipe modeli genel insan duruş modelidir. Bu durumda elle inceleme çalışmaya devam eder.

RF-DETR bağdaştırıcısı ve eğitim akışı hazır; kendi veri setinle eğitim ve ayrılmış test videolarıyla değerlendirme gerekir. Ayrıntılar [MODEL_EGITIMI.md](docs/MODEL_EGITIMI.md). ESP32 derleme ve fiziksel test durumu [TEST_RAPORU.md](docs/TEST_RAPORU.md) içinde tutulur. Kartın fiziksel bağlantısını yazılım testleri doğrulamaz.

## Belgeler ve geliştirme

- [Uçtan uca sistem haritası ve kod envanteri](docs/SISTEM_HARITASI.md)
- [Çekim ve kalibrasyon](docs/CEKIM.md)
- [Donanım, bağlantı şeması, yükleme](docs/DONANIM.md)
- [Model eğitimi ve veri etiketleme](docs/MODEL_EGITIMI.md)
- [Mühendislikte Tasarım Esasları proje taslağı](docs/PROJE.md)
- [Test ve doğrulama durumu](docs/TEST_RAPORU.md)
- [Kaynaklar ve lisanslar](THIRD_PARTY_NOTICES.md)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check tennis_tracking scripts tests
.\.venv\Scripts\python.exe -m tennis_tracking.app --demo --screenshot data/arayuz.png
```

`data/` oturumları, `models/` indirilen ağırlıkları, `datasets/` kendi görüntülerini içerir. Bunlar Git dışında tutulur. Kaynak video taşınırsa geçmiş kayıtta dosya bulunamaz; bu sürüm videoyu kopyalamaz. Yeniden analiz yeni oturum açar, eski incelemeyi korur.
