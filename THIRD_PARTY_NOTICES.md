# Kaynaklar ve üçüncü taraf bileşenleri

Bu depo kendi uygulama, entegrasyon, test ve ESP32 yazılımımızı içerir. Aşağıdaki rehberler tasarım referansıdır; paylaşılmamış kaynak kodu veya ağırlıkların kopyalandığı iddia edilmez.

| Kaynak | Kullanım |
|---|---|
| https://github.com/collidingScopes/tennis-cv | Duvar antrenmanı yaklaşımı. Yalnızca kavramsal README; rehberdeki sabit eşikler ve hız iddiaları doğrulanmış ölçümler olarak alınmadı. |
| https://github.com/ArtLabss/tennis-tracking | Maç/top takibi araştırma referansı. Depo kökündeki Unlicense, tüm harici ağırlıkların otomatik olarak aynı lisansa sahip olduğu anlamına gelmez; bu uygulamaya ağırlıkları alınmadı. |
| https://github.com/JasonHahne/Tennis_Stroke_Analyzer | MIT lisanslı teknik inceleme uygulaması; arayüz ve vücut inceleme yaklaşımı referansı. Kaynak kodu bu depoya kopyalanmadı. |
| https://github.com/roboflow/rf-detr | İsteğe bağlı RF-DETR Nano bağımlılığı. Apache-2.0 kapsamındaki Nano seçildi; Plus/XL/2XL bileşenleri kullanılmıyor. |
| https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker | MediaPipe Tasks API ve resmi Pose Landmarker Lite modeli. |
| https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html | Duvar düzlemi için perspektif dönüşümü. |
| https://github.com/adafruit/Adafruit_SSD1306 | SSD1306 Arduino kütüphanesi; BSD lisansı. PlatformIO aracılığıyla kurulur. |
| https://github.com/adafruit/Adafruit-GFX-Library | Ekran çizim kütüphanesi; PlatformIO bağımlılığı. |
| https://github.com/bblanchon/ArduinoJson | Arduino JSON ayrıştırıcısı; PlatformIO bağımlılığı. |
| https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html | ESP32 seri iletişim API'si. |

NumPy, OpenCV, PySide6, PyAV, pyserial, MediaPipe ve isteğe bağlı RF-DETR pip bağımlılıklarıdır; kaynak/lisans metinleri kurulan paketlerde ve kendi depolarında bulunur. PySide6'nın Qt dağıtım yükümlülükleri, uygulama sonradan paketlenip dağıtılırsa ayrıca korunmalıdır. Bu teslim Python kaynak projesi ve yerel sanal ortamdır.

Görüntüler ve model ağırlıkları için veri/model lisansları ayrıca değerlendirilmelidir. Eğitim aracı varsayılan olarak kullanıcının kendi çekimlerini kullanır. Örnek uygulama videosu programatik olarak üretilmiştir; sosyal medya görüntüleri projeye dahil edilmemiştir.
