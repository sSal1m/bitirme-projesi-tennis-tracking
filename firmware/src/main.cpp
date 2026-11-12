#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

Adafruit_SSD1306 display(128, 64, &Wire, -1);
String buffer;
bool screenReady = false;
bool haveSummary = false;
unsigned long lastPage = 0;
int page = 0;
int strokes = 0, forehand = 0, backhand = 0, unknown = 0, reviewed = 0, localized = 0;
float hitRate = 0, speedKmh = 0;
bool haveHit = false, haveSpeed = false;

void render() {
  if (!screenReady) return;
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("DUVAR TENIS");
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);
  display.setCursor(0, 16);
  if (!haveSummary) {
    display.println("USB baglantisi hazir");
    display.println("Sonuc bekleniyor...");
  } else if (page == 0) {
    display.print("Vurus: "); display.println(strokes);
    display.print("FH "); display.print(forehand); display.print(" / BH "); display.println(backhand);
    display.print("Belirsiz: "); display.println(unknown);
    display.print("Incelendi: "); display.print(reviewed); display.print("/"); display.println(strokes);
  } else {
    display.print("Hedef: ");
    if (haveHit) { display.print(hitRate, 1); display.println("%"); } else display.println("--");
    display.print("Konumlu: "); display.println(localized);
    display.print("Tahmin: ");
    if (haveSpeed) { display.print(speedKmh, 1); display.println(" km/h"); } else display.println("--");
    display.println("Radar hizi degildir");
  }
  display.display();
}

bool numberOrNull(JsonVariantConst value) {
  return value.isNull() || value.is<float>();
}

void receiveLine(const String &line) {
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, line);
  JsonObjectConst obj = doc.as<JsonObjectConst>();
  if (error || obj["v"].as<int>() != 1 || !obj["strokes"].is<int>() || !obj["forehand"].is<int>() ||
      !obj["backhand"].is<int>() || !obj["unknown"].is<int>() || !obj["reviewed"].is<int>() ||
      !obj["localized"].is<int>() || !numberOrNull(obj["hit_rate"]) || !numberOrNull(obj["approach_kmh"])) {
    Serial.println("{\"v\":1,\"ack\":false}");
    return;
  }
  int total = obj["strokes"].as<int>();
  int fh = obj["forehand"].as<int>(), bh = obj["backhand"].as<int>(), unk = obj["unknown"].as<int>();
  int rev = obj["reviewed"].as<int>(), loc = obj["localized"].as<int>();
  if (total < 0 || fh < 0 || bh < 0 || unk < 0 || fh + bh + unk != total || rev < 0 || rev > total ||
      loc < 0 || loc > total || (!obj["hit_rate"].isNull() && (obj["hit_rate"].as<float>() < 0 || obj["hit_rate"].as<float>() > 100)) ||
      (!obj["approach_kmh"].isNull() && obj["approach_kmh"].as<float>() < 0)) {
    Serial.println("{\"v\":1,\"ack\":false}");
    return;
  }
  strokes = total; forehand = fh; backhand = bh; unknown = unk; reviewed = rev; localized = loc;
  haveHit = !obj["hit_rate"].isNull(); hitRate = obj["hit_rate"] | 0.0f;
  haveSpeed = !obj["approach_kmh"].isNull(); speedKmh = obj["approach_kmh"] | 0.0f;
  haveSummary = true;
  page = 0;
  lastPage = millis();
  render();
  if (screenReady) Serial.println("{\"v\":1,\"ack\":true}");
  else Serial.println("{\"v\":1,\"ack\":false,\"error\":\"display\"}");
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  // Avoid acknowledging a display that is absent from the I2C bus.
  Wire.beginTransmission(0x3C);
  bool found = Wire.endTransmission() == 0;
  screenReady = found && display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  buffer.reserve(768);
  render();
}

void loop() {
  static bool dropping = false;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n') {
      if (!dropping && buffer.length()) receiveLine(buffer);
      buffer = "";
      dropping = false;
    } else if (ch != '\r' && !dropping) {
      if (buffer.length() >= 767) { buffer = ""; dropping = true; }
      else buffer += ch;
    }
  }
  if (haveSummary && millis() - lastPage > 4000) {
    lastPage = millis();
    page = 1 - page;
    render();
  }
  delay(2);
}
