// === 修复版本：Solar(A0) + Wind(A1) ===
// Solar：A0, DEFAULT(≈5V)；Wind：A1, INTERNAL(≈1.1V)

#include <Arduino.h>

// ---------- Pins ----------
const uint8_t PIN_SOLAR = A0;
const uint8_t PIN_WIND  = A1;
const uint8_t PIN_LED   = 13;   // 风转动指示

// ---------- Potentiometer Pins (for 5 dashboard knobs) ----------
const uint8_t PIN_POT1 = A2;
const uint8_t PIN_POT2 = A3;
const uint8_t PIN_POT3 = A4;
const uint8_t PIN_POT4 = A5;
const uint8_t PIN_POT5 = A6;  

// ===================== Solar =====================
const uint16_t SOLAR_SAMPLE_MS = 50;
const uint16_t SOLAR_CAL_MS    = 3000;
const float    BASE_ALPHA  = 0.0005f;
const float    NOISE_ALPHA = 0.05f;
const float    NOISE_MAX   = 30.0f;     // 恢复到 30（不是 12！）
const float    NOISE_CLIP_IN = 20.0f;   // 噪声裁剪
const int      MIN_DELTA_UP  = 20;      // 恢复绝对最小阈值  光照强度 Lichtstärkeanpassung Licht 50 30 28 25 20
const int      MIN_DELTA_DN  = 60;      // Lichtstärkeanpassung                 
const float    K_NOISE       = 7.5f;    // 噪声倍数 8.0 7.0 6.0
const float    REL_FRAC      = 0.12f;   // 相对阈值 0.15 0.13 0.12 0.1
const int      HYST          = 12;      // 滞回

enum SolarStateChar : char { AMBIENT='A', LAMP='L', BLOCKED='B' };

float baseline   = 0.0f;
float raw_ema    = 0.0f;
float noise_ema  = 5.0f;  // 修复：增大初始噪声估计
char  state      = AMBIENT;
unsigned long tSolar = 0, tSolarPrint = 0;

// ★ 修复：恢复基线更新控制
uint16_t baseline_update_counter = 0;
const uint16_t BASELINE_UPDATE_INTERVAL = 5;

// ===================== Wind =====================
const float     WIND_VREF = 1.1f;  // INTERNAL
const int       AVG_N     = 64;
const unsigned  PRINT_MS  = 200;
float TH_ON_V  = 0.03f;            // Wind_Stärke
float TH_OFF_V = 0.015f;

bool  spinning      = false;
float wind_v_ema    = 0.0f;
unsigned long tWind = 0, tWindPrint = 0;

// ===================== Potentiometers (5x) =====================
const unsigned POT_PRINT_MS = 100;  // 每 100 ms 打印一次 Poti 数值
unsigned long tPotPrint = 0;

// ===================== 分时窗口采样控制 =====================
enum Window { W_SOLAR, W_WIND };
Window curWin = W_SOLAR;
const unsigned long WINDOW_MS = 300;
unsigned long tWinStart = 0;

// 记录当前 analogReference 使用的是哪种模式
enum AnalogRefMode {
  REF_DEFAULT,
  REF_INTERNAL1V1
};

volatile AnalogRefMode gAnalogRefMode = REF_DEFAULT;

// ---------- 工具函数 ----------
static inline void warmup(uint8_t pin, uint8_t aref) {
  analogReference(aref);
  if (aref == DEFAULT) {
    gAnalogRefMode = REF_DEFAULT;
  } else if (aref == INTERNAL1V1) {
    gAnalogRefMode = REF_INTERNAL1V1;
  }
  delayMicroseconds(400);
  (void)analogRead(pin);
  (void)analogRead(pin);
  (void)analogRead(pin);
  (void)analogRead(pin);
}

static inline int analogReadAvg(uint8_t pin, int n) {
  long acc=0; 
  for(int i=0;i<n;i++){ 
    acc+=analogRead(pin); 
    delayMicroseconds(30); 
  }
  return acc / n;
}

static inline float adcToVolt(int adc, float vref){
  return adc*(vref/1023.0f);
}

// ★ 修复：添加平滑读取函数（来自 Solar_2.ino）
int readSmoothAnalog(uint8_t pin, uint8_t n=8) {
  long acc = 0;
  for (uint8_t i=0; i<n; ++i) acc += analogRead(pin);
  return (int)(acc / n);
}

// 读取 5 个 Poti，并输出一行串口数据：POTS: v1,v2,v3,v4,v5
void readAndPrintPots() {
  AnalogRefMode prevRef = gAnalogRefMode;

  if (prevRef != REF_DEFAULT) {
    analogReference(DEFAULT);
    gAnalogRefMode = REF_DEFAULT;
    delayMicroseconds(200);
  }

  int v1 = analogReadAvg(PIN_POT1, 4);
  int v2 = analogReadAvg(PIN_POT2, 4);
  int v3 = analogReadAvg(PIN_POT3, 4);
  int v4 = analogReadAvg(PIN_POT4, 4);
  int v5 = analogReadAvg(PIN_POT5, 4);

  Serial.print(F("POTS: "));
  Serial.print(v1); Serial.print(',');
  Serial.print(v2); Serial.print(',');
  Serial.print(v3); Serial.print(',');
  Serial.print(v4); Serial.print(',');
  Serial.println(v5);

  if (prevRef == REF_INTERNAL1V1) {
    analogReference(INTERNAL1V1);
    gAnalogRefMode = REF_INTERNAL1V1;
    delayMicroseconds(200);
  }
}

// ===================== Setup =====================
void setup() {
  pinMode(PIN_SOLAR, INPUT);
  pinMode(PIN_WIND,  INPUT);
  pinMode(PIN_LED,   OUTPUT);
  digitalWrite(PIN_LED, LOW);

  Serial.begin(9600);
  while(!Serial){}

  // —— Solar：校准（使用 Solar_2.ino 的方法） —— 
  curWin = W_SOLAR;
  tWinStart = millis();

  {
    warmup(PIN_SOLAR, DEFAULT);       // 5V参考 + 预热
    unsigned long t0 = millis();
    long acc=0, cnt=0;
    while(millis() - t0 < SOLAR_CAL_MS){
      acc += readSmoothAnalog(PIN_SOLAR, 8);  // ★ 使用平滑读取
      cnt++;
      delay(10);
    }
    baseline = cnt ? (float)acc/cnt : 0.0f;
    raw_ema  = baseline;
    noise_ema= 5.0f;  // ★ 修复：更大的初始噪声估计
    state    = AMBIENT;
    baseline_update_counter = 0;  // ★ 修复：初始化计数器
    tSolar = tSolarPrint = millis();

    Serial.print("Initial baseline: "); Serial.println(baseline);
    Serial.print("raw=");   Serial.print((int)round(raw_ema));
    Serial.print(",base="); Serial.print((int)round(baseline));
    Serial.print(",state=");Serial.println((char)state);
  }

  // —— Wind：初始化 —— 
  warmup(PIN_WIND, INTERNAL1V1);
  {
    int   adc = analogReadAvg(PIN_WIND, AVG_N);
    float v   = adcToVolt(adc, WIND_VREF);
    wind_v_ema = v;
    spinning = (v >= TH_ON_V);
    digitalWrite(PIN_LED, spinning ? HIGH : LOW);
    tWind = tWindPrint = millis();

    Serial.print(F("ADC="));    Serial.print(adc);
    Serial.print(F("  V(A1)=")); Serial.print(v,3); Serial.print(F(" V  "));
    Serial.println(spinning ? F("[SPINNING]") : F("[STOPPED]"));
  }
}

// ===================== Loop =====================
void loop() {
  const unsigned long now = millis();

  // —— 定期读取 5 个 Poti 并发送到串口 ——
  if (now - tPotPrint >= POT_PRINT_MS) {
    tPotPrint = now;
    readAndPrintPots();
  }

  // —— 窗口切换 ——
  if(now - tWinStart >= WINDOW_MS){
    tWinStart = now;
    if(curWin == W_SOLAR){
      curWin = W_WIND;
      warmup(PIN_WIND, INTERNAL1V1);
      tWind = now;
    }else{
      curWin = W_SOLAR;
      warmup(PIN_SOLAR, DEFAULT);
      tSolar = now;
    }
  }

  // ================= Solar 窗口（使用 Solar_2.ino 的改进逻辑） =================
  if(curWin == W_SOLAR){
    if(now - tSolar >= SOLAR_SAMPLE_MS){
      tSolar = now;

      int   raw_val = readSmoothAnalog(PIN_SOLAR, 8);  // ★ 修复：使用平滑读取
      float raw = (float)raw_val;
      float diff = raw - baseline;

      // ★ 修复：仅在 AMBIENT 时更新噪声（来自 Solar_2.ino）
      if (state == AMBIENT) {
        float nd = fabs(diff);
        if (nd > NOISE_CLIP_IN) nd = NOISE_CLIP_IN;  // ★ 修复：噪声裁剪
        noise_ema = (1.0f - NOISE_ALPHA) * noise_ema + NOISE_ALPHA * nd;
        if (noise_ema > NOISE_MAX) noise_ema = NOISE_MAX;
      }

      // ★ 修复：使用 Solar_2.ino 的完整阈值计算
      float rel_base = baseline;
      if (rel_base < 60.0f) rel_base = 60.0f;
      float rel_th = REL_FRAC * rel_base;
      float up_th = max((float)MIN_DELTA_UP, max(K_NOISE * noise_ema, rel_th));
      float dn_th = max((float)MIN_DELTA_DN, max(K_NOISE * noise_ema, rel_th));

      // ★ 修复：使用 Solar_2.ino 的状态机逻辑
      char newState = state;
      switch (state) {
        case AMBIENT:
          if (diff > up_th)        newState = LAMP;
          else if (diff < -dn_th)  newState = BLOCKED;
          else {
            // ★ 修复：恢复基线更新控制
            baseline_update_counter++;
            if (baseline_update_counter >= BASELINE_UPDATE_INTERVAL) {
              baseline = (1.0f - BASE_ALPHA) * baseline + BASE_ALPHA * raw;
              baseline_update_counter = 0;
            }
          }
          break;
         
        case LAMP:
          if (diff < up_th - HYST)  newState = AMBIENT;  // ★ 修复：使用滞回
          break;
         
        case BLOCKED:
          if (diff > -(dn_th - HYST)) newState = AMBIENT;  // ★ 修复：使用滞回
          break;
      }

      // ★ 修复：状态转换时的噪声处理（来自 Solar_2.ino）
      if ((state == LAMP || state == BLOCKED) && newState == AMBIENT) {
        noise_ema = max(2.0f, noise_ema * 0.7f);  // 不要太激进
      }

      bool changed = (newState != state);
      state = newState;

      if (changed || (now - tSolarPrint >= 200)){
        tSolarPrint = now;
        Serial.print("raw=");   Serial.print(raw_val);
        Serial.print(",base="); Serial.print((int)round(baseline));
        Serial.print(",state=");Serial.println((char)state);
      }
    }
  }

  // ================= Wind 窗口（保持不变） =================
  else { // curWin == W_WIND
    if(now - tWind >= SOLAR_SAMPLE_MS){
      tWind = now;

      int   adc = analogReadAvg(PIN_WIND, AVG_N);
      float vA1 = adcToVolt(adc, WIND_VREF);

      const float ALPHA_WIND = 0.25f;
      wind_v_ema = ALPHA_WIND*vA1 + (1.0f - ALPHA_WIND)*wind_v_ema;

      if(!spinning && wind_v_ema >= TH_ON_V)  spinning = true;
      if( spinning && wind_v_ema <= TH_OFF_V) spinning = false;

      digitalWrite(PIN_LED, spinning ? HIGH : LOW);

      if(now - tWindPrint >= PRINT_MS){
        tWindPrint = now;
        Serial.print(F("ADC="));    Serial.print(adc);
        Serial.print(F("  V(A1)=")); Serial.print(wind_v_ema,3); Serial.print(F(" V  "));
        Serial.println(spinning ? F("[SPINNING]") : F("[STOPPED]"));
      }
    }
  }
}