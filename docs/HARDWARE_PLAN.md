# Donanım görevi — uygulama planı

> ⚠️ **KAPSAM DIŞI (Kasım 2026).** Donanım bölümü projeden çıkarıldı. Bu belge
> gelecekte kapsama geri alınırsa kullanılmak üzere saklanır; **teslim materyali
> değildir** ve fiziksel doğrulama yapılmamıştır. Kart yazılımı 12 Kasım 2026'da
> başarıyla derlenmiştir, protokol bilgisayar tarafında test edilmiştir.
> Ayrıntılı güncel iş planı: [DATA_PLAN.md](DATA_PLAN.md)

**Sorumlu:** Saib Alsaeid (donanım birinciliği)
**Kapsam:** ESP32 + SSD1306 OLED sonuç ekranı, fiziksel kurulum ve doğrulama
**Durum (12 Kasım 2026):** Yazılım derlendi ✔ · Bilgisayar tarafı protokol test edildi ✔ · Fiziksel test bekliyor ✘

---

## 0. Bugün tamamlanan işler (başlangıçtan önce hazır)

| İş | Durum | Kanıt |
|---|---|---|
| PlatformIO 6.2.0 kurulumu | ✔ | `.venv` içine kuruldu |
| `espressif32@6.10.0` + `esp32dev` derlemesi | ✔ | `firmware/.pio/build/esp32dev/firmware.bin` |
| ArduinoJson 7 hatası | ✔ çözülmüş | `JsonObjectConst` okuması derlendi |
| Kaynak kullanımı | ✔ | RAM %6.7 · Flash %23.4 |
| Protokol sözleşmesi testi | ✔ | `tests/test_hardware_protocol.py` (10 test) |
| Toplam test sayısı | ✔ | 74 test geçiyor |

> **Artık kart eline geldiği anda yapman gereken tek şey: bağla, yükle, test et.**

---

## 1. Malzeme listesi

| Parça | Adet | Kritik özellik | Not |
|---|---:|---|---|
| ESP32 DevKit V1 (ESP32-WROOM-32) | 1 | USB-seri dönüştürücülü | ESP32-C3/S3 **almayın**, pin planı farklı |
| SSD1306 OLED | 1 | 128×64, I²C, **0x3C**, 3.3 V | SH1106 değil, SSD1306 olmalı |
| USB veri kablosu | 1 | **veri** kablosu (şarj değil) | Micro-USB / USB-C uyumuna dikkat |
| Breadboard + jumper kablo | 1 set | | |
| 1.5 mAh/200 mAh güç kaynağı (opsiyonel) | 1 | | Sunumda taşınabilirlik için |

**Alışveriş notları:** Modülün üzerinde **4 pin (GND-VCC-SCL-SDA)** varsayımı yapılmış; 4 pinli modül al. Pin sayısı 3 veya 7 olan modellerden kaçın.

---

## 2. Bağlantı şeması

```
        ESP32 DevKit V1
        ┌──────────────┐
        │          3V3 ├───► OLED VCC
        │           GND ├───► OLED GND
        │         GPIO21├───► OLED SDA
        │         GPIO22├───► OLED SCL
        │              │
        │         USB ─┘  (bilgisayar)
        └──────────────┘
```

- Kablolamayı **USB çıkarık** yap.
- Güç bilgisayarın USB portundan gelir; OLED 3V3 hattına bağlanır.
- Kart açılışta `0x3C` adresine yanıt olup olmadığını kontrol eder; ekran yoksa `ack:false` döner.

---

## 3. Derleme ve yükleme

```powershell
# Derleme (ilk seferinde araç zinciri indirildiği için ~14 dk)
.\.venv\Scripts\python.exe -m platformio run -d firmware

# Yükleme (COM5 yerine kendi portunu yaz)
.\.venv\Scripts\python.exe -m platformio run -d firmware --target upload --upload-port COM5

# Portlarını listele
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
```

**Yükleme yapmıyorsa:** BOOT düğmesine basılı tutup RESET'e bas, sonra BOOT'u bırak (download mode), sonra tekrar yükle.
**Seri monitörü kapat** — aynı COM portunu iki program paylaşamaz.

---

## 4. Fiziksel kabul testi (5 adım)

| # | Adım | Beklenen |
|---|------|----------|
| 1 | Kartı USB'den başlat | OLED'de "USB baglantisi hazir / Sonuc bekleniyor..." |
| 2 | Uygulamadan örnek oturumu gönder | Ekranda 5 vuruş, 4/1 dağılımı, %80 isabet — bilgisayarla aynı |
| 3 | Mesafesiz gerçek oturum gönder | Hız alanı `--` görünmeli |
| 4 | USB'yi çıkar/tak, tekrar gönder | Uygulama sonuçları kaybetmemeli |
| 5 | Ekran bağlantısı olmadan başlat | Uygulama başarılı gönderim bildirmemeli |

### Uygulamadan gönderim
Uygulama → **Donanım ekranı** → *Portları yenile* → COM portunu seç → *Sonuçları ekrana gönder*
Sonuç: `{"v":1,"ack":true}` → OLED'de iki sayfa 4 saniyede bir değişir.

**Sayfa 1:** Vurus / FH / BH / Belirsiz / Incelendi
**Sayfa 2:** Hedef % / Konumlu / Tahmin (km/sa) / "Radar hizi degildir"

---

## 5. Sıralama başarısı ölçümü

Proje hedefi: **20/20 özet ≤ 6 sn**, ACK doğru, OLED sayacı doğru.

```python
# send_summary() her çağrıda 3 sn ACK bekler; 20 kez arka arkaya çalıştır.
```

Ölçüm tablosu:

| Gönderim | Süre (sn) | ACK | OLED doğru? | Not |
|---:|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| … | | | | |
| 20 | | | | |
| **ortalama** | | | | |
| **maksimum** | | | | |

---

## 6. Sık karşılaşılan sorunlar

| Belirti | Sebep | Çözüm |
|---|---|---|
| `ack:false, error:display` | OLED yok / yanlış adres / kablo ters | 0x3C adresini doğrula, SDA/SCL değiştir |
| Hiç `ack` gelmiyor | Yanlış COM portu / port meşgul | Seri monitörü kapat, portu seç |
| Ekran açık ama boş | Yanlış SSD1306 sürücüsü | Adafruit SSD1306 @2.5.13 kullanılıyor, kontrol et |
| Yükleme başarısız | Download mode'a girmedi | BOOT+RESET yöntemi |
| Ekran yanıyor ama `ack:false` | I²C kablo kopuk | Kabloları değiştir |

---

## 7. Teslim için gereken belgeler

- [ ] Fotoğraf: bağlantı şeması gerçek haliyle
- [ ] Fotoğraf: OLED'de çalışan sonuç ekranı (her iki sayfa)
- [ ] Video: uygulamadan gönderim → OLED güncellenmesi
- [ ] Tablo: 20 gönderim süre ölçümü
- [ ] `docs/TEST_RAPORU.md` içine fiziksel test sonucu
- [ ] Parça listesi + gerçek maliyet tablosu (proje dokümanı "düşük başlangıç maliyeti" maddesi)

---

## 8. Bu hafta hedef

| Gün | İş | Çıktı |
|---|---|---|
| 1 | Malzemeleri temin et + bağlantı | Fotoğraf |
| 2 | Kartı yükle + ekranı çalıştır | "USB baglantisi hazir" ekranı |
| 3 | Uygulamadan gönderim testi | ack:true + OLED sayacı |
| 4 | 20 gönderim ölçümü + kablo kopma testi | Ölçüm tablosu |
| 5 | Fotoğraf/video + TEST_RAPORU güncelleme | Teslim materyali |
