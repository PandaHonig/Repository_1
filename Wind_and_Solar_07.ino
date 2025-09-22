// === Unified Solar(A0) + Wind(A1) — 参数与判定保持原样；仅把 NOISE_MAX 调回 12 ===
// Solar：A0, DEFAULT(≈5V)；Wind：A1, INTERNAL(≈1.1V)

#include <Arduino.h>

// ---------- Pins ----------
const uint8_t PIN_SOLAR = A0;
const uint8_t PIN_WIND  = A1;
const uint8_t PIN_LED   = 13;   // 风转动指示

// ===================== Solar（你的原逻辑/语义） =====================
const uint16_t SOLAR_SAMPLE_MS = 50;
const uint16_t SOLAR_CAL_MS    = 3000;
const float    BASE_ALPHA  = 0.0005f;
const float    NOISE_ALPHA = 0.05f;
const float    NOISE_MAX   = 12.0f;     // ★ 关键：把上限调到 12（避免高阈值被顶到过高）
const int      SOLAR_MIN_LOW  = 12;
const int      SOLAR_MIN_HIGH = 40;
const float    SOLAR_K_LOW    = 3.0f;
const float    SOLAR_K_HIGH   = 8.0f;

enum SolarStateChar : char { AMBIENT='A', LAMP='L', BLOCKED='B' };

float baseline   = 0.0f;
float raw_ema    = 0.0f;
float noise_ema  = 2.0f;
char  state      = AMBIENT;
unsigned long tSolar = 0, tSolarPrint = 0;

// ===================== Wind（你的原逻辑/阈值） =====================
const float     WIND_VREF = 1.1f;  // INTERNAL
const int       AVG_N     = 64;
const unsigned  PRINT_MS  = 200;
float TH_ON_V  = 0.06f;            // AA118 迟滞阈值
float TH_OFF_V = 0.03f;

bool  spinning      = false;
float wind_v_ema    = 0.0f;
unsigned long tWind = 0, tWindPrint = 0;

// ===================== 分时窗口采样控制 =====================
enum Window { W_SOLAR, W_WIND };
Window curWin = W_SOLAR;
const unsigned long WINDOW_MS = 300;
unsigned long tWinStart = 0;

// ---------- 工具：目标引脚预热（切参考后延时+多次丢弃） ----------
static inline void warmup(uint8_t pin, uint8_t aref) {
  analogReference(aref);
  delayMicroseconds(400);
  (void)analogRead(pin);
  (void)analogRead(pin);
  (void)analogRead(pin);
  (void)analogRead(pin);
}
static inline int analogReadAvg(uint8_t pin, int n) {
  long acc=0; for(int i=0;i<n;i++){ acc+=analogRead(pin); delayMicroseconds(30); }
  return acc / n;
}
static inline float adcToVolt(int adc, float vref){ return adc*(vref/1023.0f); }

// ===================== Setup =====================
void setup() {
  pinMode(PIN_SOLAR, INPUT);
  pinMode(PIN_WIND,  INPUT);
  pinMode(PIN_LED,   OUTPUT);
  digitalWrite(PIN_LED, LOW);

  Serial.begin(9600);
  while(!Serial){}

  // —— Solar：请在“环境光”下校准 3 秒 —— 
  curWin = W_SOLAR;
  tWinStart = millis();

  {
    unsigned long t0 = millis();
    long acc=0, cnt=0;
    warmup(PIN_SOLAR, DEFAULT);       // 5V参考 + 目标引脚预热
    while(millis() - t0 < SOLAR_CAL_MS){
      acc += analogRead(PIN_SOLAR);
      cnt++;
      delay(2);
    }
    float avg = cnt ? (float)acc/cnt : 0.0f;
    baseline = avg;
    raw_ema  = avg;
    noise_ema= 2.0f;
    state    = AMBIENT;               // 基线附近 = 环境光 = A
    tSolar = tSolarPrint = millis();

    // 输出（保持原格式）
    Serial.print("raw=");   Serial.print((int)round(raw_ema));
    Serial.print(",base="); Serial.print((int)round(baseline));
    Serial.print(",state=");Serial.println((char)state);
  }

  // —— Wind：初始化一次，真正采样在 Wind 窗口进行 —— 
  warmup(PIN_WIND, INTERNAL);         // 1.1V参考 + 目标引脚预热
  {
    int   adc = analogReadAvg(PIN_WIND, AVG_N);
    float v   = adcToVolt(adc, WIND_VREF);
    wind_v_ema = v;
    spinning = (v >= TH_ON_V);
    digitalWrite(PIN_LED, spinning ? HIGH : LOW);
    tWind = tWindPrint = millis();

    // 输出（保持原格式）
    Serial.print(F("ADC="));    Serial.print(adc);
    Serial.print(F("  V(A1)=")); Serial.print(v,3); Serial.print(F(" V  "));
    Serial.println(spinning ? F("[SPINNING]") : F("[STOPPED]"));
  }
}

// ===================== Loop =====================
void loop() {
  const unsigned long now = millis();

  // —— 窗口切换 —— 
  if(now - tWinStart >= WINDOW_MS){
    tWinStart = now;
    if(curWin == W_SOLAR){
      curWin = W_WIND;
      warmup(PIN_WIND, INTERNAL);
      tWind = now;
    }else{
      curWin = W_SOLAR;
      warmup(PIN_SOLAR, DEFAULT);
      tSolar = now;
    }
  }

  // ================= Solar 窗口（5V参考） =================
  if(curWin == W_SOLAR){
    if(now - tSolar >= SOLAR_SAMPLE_MS){
      tSolar = now;

      int   a   = analogRead(PIN_SOLAR);
      float raw = (float)a;

      // 原始值 EMA
      raw_ema = NOISE_ALPHA*raw + (1.0f - NOISE_ALPHA)*raw_ema;

      // 噪声估计（上限 NOISE_MAX = 12）
      float diff = fabsf(raw_ema - baseline);
      noise_ema  = NOISE_ALPHA*diff + (1.0f - NOISE_ALPHA)*noise_ema;
      if(noise_ema > NOISE_MAX) noise_ema = NOISE_MAX;

      // 阈值（自适应 + 最小门槛）
      float lowThr  = max((float)SOLAR_MIN_LOW,  SOLAR_K_LOW  * noise_ema);
      float highThr = max((float)SOLAR_MIN_HIGH, SOLAR_K_HIGH * noise_ema);

      // 与基线的偏差
      float delta = raw_ema - baseline;

      // 仅在“接近基线”时缓慢跟踪（环境光附近才跟）
      if (fabs(delta) <= lowThr) {
        baseline = BASE_ALPHA*raw_ema + (1.0f - BASE_ALPHA)*baseline;
      }

      // 判定：更亮→LAMP；更暗→BLOCKED；其余→AMBIENT
      char newState;
      if      (delta >=  highThr) newState = LAMP;
      else if (delta <= -lowThr ) newState = BLOCKED;
      else                        newState = AMBIENT;

      // 回到 AMBIENT 时的噪声处理（你的原句保留）
      if ((state == LAMP || state == BLOCKED) && newState == AMBIENT) {
        noise_ema = max(2.0f, noise_ema * 0.7f);
      }

      bool changed = (newState != state);
      state = newState;

      if (changed || (now - tSolarPrint >= 200)){
        tSolarPrint = now;
        Serial.print("raw=");   Serial.print((int)round(raw_ema));
        Serial.print(",base="); Serial.print((int)round(baseline));
        Serial.print(",state=");Serial.println((char)state);
      }
    }
  }

  // ================= Wind 窗口（1.1V参考） =================
  else { // curWin == W_WIND
    if(now - tWind >= SOLAR_SAMPLE_MS){
      tWind = now;

      int   adc = analogReadAvg(PIN_WIND, AVG_N);        // 64 次平均
      float vA1 = adcToVolt(adc, WIND_VREF);

      // 轻度 EMA（稳定读数）
      const float ALPHA_WIND = 0.25f;
      wind_v_ema = ALPHA_WIND*vA1 + (1.0f - ALPHA_WIND)*wind_v_ema;

      // 迟滞判定（原阈值）
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

