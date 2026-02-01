// Solar：A0, DEFAULT(≈5V)；Wind：A1, INTERNAL(≈1.1V)

#include <Arduino.h>
#include <AccelStepper.h>
#include <FastLED.h>
#include <math.h>

// ---------- Pins ----------
const uint8_t PIN_SOLAR = A0;
const uint8_t PIN_WIND  = A1;


// ---------- Potentiometer Pins (for 5 dashboard knobs) ----------
const uint8_t PIN_POT1 = A2;
const uint8_t PIN_POT2 = A3;
const uint8_t PIN_POT3 = A4;
const uint8_t PIN_POT4 = A5;
const uint8_t PIN_POT5 = A6;

// ---------- Motor Pins ----------
// Motor 1..7: STEP, DIR, ENABLE 引脚  1<7 5<6
const uint8_t MOTOR7_STEP_PIN   = 22;
const uint8_t MOTOR7_DIR_PIN    = 23;
const uint8_t MOTOR7_ENABLE_PIN = 24;

const uint8_t MOTOR2_STEP_PIN   = 25;
const uint8_t MOTOR2_DIR_PIN    = 26;
const uint8_t MOTOR2_ENABLE_PIN = 27;

const uint8_t MOTOR3_STEP_PIN   = 28;
const uint8_t MOTOR3_DIR_PIN    = 29;
const uint8_t MOTOR3_ENABLE_PIN = 30;

const uint8_t MOTOR4_STEP_PIN   = 31;
const uint8_t MOTOR4_DIR_PIN    = 32;
const uint8_t MOTOR4_ENABLE_PIN = 33;

const uint8_t MOTOR6_STEP_PIN   = 34;
const uint8_t MOTOR6_DIR_PIN    = 35;
const uint8_t MOTOR6_ENABLE_PIN = 36;

const uint8_t MOTOR5_STEP_PIN   = 37;
const uint8_t MOTOR5_DIR_PIN    = 38;
const uint8_t MOTOR5_ENABLE_PIN = 39;

const uint8_t MOTOR1_STEP_PIN   = 40;
const uint8_t MOTOR1_DIR_PIN    = 41;
const uint8_t MOTOR1_ENABLE_PIN = 42;

// ---------- LED Pins & Sizes ----------
#define DATA_PIN_LED1 50
#define DATA_PIN_LED2 51
#define DATA_PIN_LED3 52
#define DATA_PIN_LED4 53
#define DATA_PIN_LED5 49 

#define NUM_LEDS_LED1 32
#define NUM_LEDS_LED2 26
#define NUM_LEDS_LED3 9
#define NUM_LEDS_LED4 15
#define NUM_LEDS_LED5 65

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

// ===================== Motor / LED 全局变量 =====================
// Poti 映射得到的 rate（0.0 ~ 1.0）
float meter_reuse_rate                = 0.0f;
float impeller_remanufacturing_rate   = 0.0f;
float housing_remanufacturing_rate    = 0.0f;
float impeller_recycling_rate         = 0.0f;
float housing_recycling_rate          = 0.0f;

// 从 Python 传来的 Energiemix（0.0 ~ 1.0）
float solar_energy_share = 0.0f;
float wind_energy_share  = 0.0f;

// 步进电机参数
const float MOTOR_MAX_RPM = 200.0f;
const float STEPS_PER_REVOLUTION = 400.0f; // full-step 200 half 400
const float MOTOR_MAX_STEPS_PER_SECOND =
    MOTOR_MAX_RPM / 60.0f * STEPS_PER_REVOLUTION;
const float MIN_STEPS_PER_SECOND_FOR_ENABLE = 1.0f;

// LED 动画参数
const uint8_t LED_GLOBAL_BRIGHTNESS = 50;
const float LED_FLOW_SPEED_MAX    = 8.0f;
const float LED_ENERGY_SPEED_MAX  = 12.0f;

const int8_t LED1_DIR_SIGN = -1;
const int8_t LED4_DIR_SIGN = -1;
const int8_t LED5_DIR_SIGN = -1;

CRGB leds1[NUM_LEDS_LED1];
CRGB leds2[NUM_LEDS_LED2];
CRGB leds3[NUM_LEDS_LED3];
CRGB leds4[NUM_LEDS_LED4];
CRGB leds5[NUM_LEDS_LED5];

float led1_impeller_pos = 0.0f;
float led1_housing_pos  = 0.0f;

float led2_impeller_pos = 0.0f;
float led2_housing_pos  = 0.0f;

float led3_waste_pos    = 0.0f;
float led4_raw_pos      = 0.0f;

float led5_solar_pos    = 0.0f;
float led5_wind_pos     = 0.0f;

unsigned long last_led_update_ms = 0;

// 步进电机实例
AccelStepper motor1(AccelStepper::DRIVER, MOTOR1_STEP_PIN, MOTOR1_DIR_PIN);
AccelStepper motor2(AccelStepper::DRIVER, MOTOR2_STEP_PIN, MOTOR2_DIR_PIN);
AccelStepper motor3(AccelStepper::DRIVER, MOTOR3_STEP_PIN, MOTOR3_DIR_PIN);
AccelStepper motor4(AccelStepper::DRIVER, MOTOR4_STEP_PIN, MOTOR4_DIR_PIN);
AccelStepper motor5(AccelStepper::DRIVER, MOTOR5_STEP_PIN, MOTOR5_DIR_PIN);
AccelStepper motor6(AccelStepper::DRIVER, MOTOR6_STEP_PIN, MOTOR6_DIR_PIN);
AccelStepper motor7(AccelStepper::DRIVER, MOTOR7_STEP_PIN, MOTOR7_DIR_PIN);

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

bool parseEmixLine(const String& line, float& solar, float& wind) {
  solar = 0.0f;
  wind  = 0.0f;

  int iS = line.indexOf("solar=");
  int iW = line.indexOf("wind=");
  if (iS < 0 || iW < 0) return false;

  int comma = line.indexOf(',', iS);
  if (comma < 0) return false;

  String sSolar = line.substring(iS + 6, comma);
  String sWind  = line.substring(iW + 5);

  // 允许逗号后有空格：", wind=..."
  sSolar.trim();
  sWind.trim();

  solar = sSolar.toFloat();
  wind  = sWind.toFloat();

  // clamp to 0..1
  if (solar < 0.0f) solar = 0.0f;
  if (solar > 1.0f) solar = 1.0f;
  if (wind  < 0.0f) wind  = 0.0f;
  if (wind  > 1.0f) wind  = 1.0f;

  return true;
}

void applyMotorSpeed(AccelStepper& motor,
                     uint8_t enablePin,
                     float stepsPerSecond)
{
  float absSpeed = fabsf(stepsPerSecond);

  if (absSpeed < MIN_STEPS_PER_SECOND_FOR_ENABLE) {
    digitalWrite(enablePin, HIGH);
    motor.setSpeed(0.0f);
  } else {
    digitalWrite(enablePin, LOW);
    motor.setSpeed(stepsPerSecond);
  }
}

void updateMotorsFromRates()
{
  float motor1_rpm_fraction = 1.0f;
  float motor2_rpm_fraction = meter_reuse_rate;

  float fraction_new_meters = 1.0f - meter_reuse_rate;
  float motor3_rpm_fraction = fraction_new_meters * impeller_remanufacturing_rate;
  float motor4_rpm_fraction = fraction_new_meters * housing_remanufacturing_rate;

  float motor5_rpm_fraction = fraction_new_meters;

  float fraction_new_impeller_components =
      fraction_new_meters * (1.0f - impeller_remanufacturing_rate);
  float fraction_new_housing_components  =
      fraction_new_meters * (1.0f - housing_remanufacturing_rate);

  float motor6_rpm_fraction = fraction_new_impeller_components;
  float motor7_rpm_fraction = fraction_new_housing_components;

  float s1 = motor1_rpm_fraction * MOTOR_MAX_STEPS_PER_SECOND * -1;
  float s2 = motor2_rpm_fraction * MOTOR_MAX_STEPS_PER_SECOND * -1;
  float s3 = motor3_rpm_fraction * MOTOR_MAX_STEPS_PER_SECOND;
  float s4 = motor4_rpm_fraction * MOTOR_MAX_STEPS_PER_SECOND * -1;
  float s5 = motor5_rpm_fraction * MOTOR_MAX_STEPS_PER_SECOND;
  float s6 = motor6_rpm_fraction * MOTOR_MAX_STEPS_PER_SECOND;
  float s7 = motor7_rpm_fraction * MOTOR_MAX_STEPS_PER_SECOND * -1;

  applyMotorSpeed(motor1, MOTOR1_ENABLE_PIN, s1);
  applyMotorSpeed(motor2, MOTOR2_ENABLE_PIN, s2);
  applyMotorSpeed(motor3, MOTOR3_ENABLE_PIN, s3);
  applyMotorSpeed(motor4, MOTOR4_ENABLE_PIN, s4);
  applyMotorSpeed(motor5, MOTOR5_ENABLE_PIN, s5);
  applyMotorSpeed(motor6, MOTOR6_ENABLE_PIN, s6);
  applyMotorSpeed(motor7, MOTOR7_ENABLE_PIN, s7);
}

void updateLedsFromRates()
{
  unsigned long now = millis();
  float dt = (now - last_led_update_ms) / 1000.0f;
  if (dt <= 0.0f) return;
  last_led_update_ms = now;

  float speed_led1_impeller = LED_FLOW_SPEED_MAX
      * (1.0f - meter_reuse_rate)
      * (1.0f - impeller_remanufacturing_rate);

  float speed_led1_housing = LED_FLOW_SPEED_MAX
      * (1.0f - meter_reuse_rate)
      * (1.0f - housing_remanufacturing_rate);

  led1_impeller_pos += speed_led1_impeller * LED1_DIR_SIGN * dt;
  led1_housing_pos  += speed_led1_housing  * LED1_DIR_SIGN * dt;

  while (led1_impeller_pos >= NUM_LEDS_LED1) led1_impeller_pos -= NUM_LEDS_LED1;
  while (led1_housing_pos  >= NUM_LEDS_LED1) led1_housing_pos  -= NUM_LEDS_LED1;
  while (led1_impeller_pos < 0) led1_impeller_pos += NUM_LEDS_LED1;
  while (led1_housing_pos  < 0) led1_housing_pos  += NUM_LEDS_LED1;

  fill_solid(leds1, NUM_LEDS_LED1, CRGB::Black);
  leds1[(int)led1_impeller_pos] = CRGB::White;
  leds1[(int)led1_housing_pos]  = CRGB::Yellow;

  float speed_led2_impeller = LED_FLOW_SPEED_MAX
      * (1.0f - meter_reuse_rate)
      * (1.0f - impeller_remanufacturing_rate)
      * impeller_recycling_rate;

  float speed_led2_housing = LED_FLOW_SPEED_MAX
      * (1.0f - meter_reuse_rate)
      * (1.0f - housing_remanufacturing_rate)
      * housing_recycling_rate;

  led2_impeller_pos += speed_led2_impeller * dt;
  led2_housing_pos  += speed_led2_housing  * dt;

  if (led2_impeller_pos >= NUM_LEDS_LED2) led2_impeller_pos -= NUM_LEDS_LED2;
  if (led2_housing_pos  >= NUM_LEDS_LED2) led2_housing_pos  -= NUM_LEDS_LED2;

  fill_solid(leds2, NUM_LEDS_LED2, CRGB::Black);
  leds2[(int)led2_impeller_pos] = CRGB::White;
  leds2[(int)led2_housing_pos]  = CRGB::Yellow;

  float waste_impeller_fraction =
      (1.0f - meter_reuse_rate)
      * (1.0f - impeller_remanufacturing_rate)
      * (1.0f - impeller_recycling_rate);

  float waste_housing_fraction =
      (1.0f - meter_reuse_rate)
      * (1.0f - housing_remanufacturing_rate)
      * (1.0f - housing_recycling_rate);

  float speed_led3_waste = LED_FLOW_SPEED_MAX
      * (waste_impeller_fraction + waste_housing_fraction);

  led3_waste_pos += speed_led3_waste * dt;
  if (led3_waste_pos >= NUM_LEDS_LED3) led3_waste_pos -= NUM_LEDS_LED3;

  fill_solid(leds3, NUM_LEDS_LED3, CRGB::Black);
  leds3[(int)led3_waste_pos] = CRGB::Red;

  float speed_led4_raw = speed_led3_waste;

  led4_raw_pos += speed_led4_raw * LED4_DIR_SIGN * dt;
  while (led4_raw_pos >= NUM_LEDS_LED4) led4_raw_pos -= NUM_LEDS_LED4;
  while (led4_raw_pos < 0) led4_raw_pos += NUM_LEDS_LED4;

  fill_solid(leds4, NUM_LEDS_LED4, CRGB::Black);
  leds4[(int)led4_raw_pos] = CRGB::Purple;

  float speed_led5_solar = LED_ENERGY_SPEED_MAX * solar_energy_share;
  float speed_led5_wind  = LED_ENERGY_SPEED_MAX * wind_energy_share;

  led5_solar_pos += speed_led5_solar * LED5_DIR_SIGN * dt;
  led5_wind_pos  += speed_led5_wind  * LED5_DIR_SIGN * dt;

  while (led5_solar_pos >= NUM_LEDS_LED5) led5_solar_pos -= NUM_LEDS_LED5;
  while (led5_wind_pos  >= NUM_LEDS_LED5) led5_wind_pos  -= NUM_LEDS_LED5;
  while (led5_solar_pos < 0) led5_solar_pos += NUM_LEDS_LED5;
  while (led5_wind_pos  < 0) led5_wind_pos  += NUM_LEDS_LED5;

  fill_solid(leds5, NUM_LEDS_LED5, CRGB::Black);
  leds5[(int)led5_solar_pos] = CRGB::Orange;
  leds5[(int)led5_wind_pos]  = CRGB::Green;

  FastLED.show();
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

  meter_reuse_rate              = constrain(v1, 0, 1023) / 1023.0f;
  impeller_remanufacturing_rate = constrain(v2, 0, 1023) / 1023.0f;
  housing_remanufacturing_rate  = constrain(v3, 0, 1023) / 1023.0f;
  impeller_recycling_rate       = constrain(v4, 0, 1023) / 1023.0f;
  housing_recycling_rate        = constrain(v5, 0, 1023) / 1023.0f;

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
  

  Serial.begin(115200);
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
    
    tWind = tWindPrint = millis();

    Serial.print(F("ADC="));    Serial.print(adc);
    Serial.print(F("  V(A1)=")); Serial.print(v,3); Serial.print(F(" V  "));
    Serial.println(spinning ? F("[SPINNING]") : F("[STOPPED]"));
  }

  pinMode(MOTOR1_ENABLE_PIN, OUTPUT);
  pinMode(MOTOR2_ENABLE_PIN, OUTPUT);
  pinMode(MOTOR3_ENABLE_PIN, OUTPUT);
  pinMode(MOTOR4_ENABLE_PIN, OUTPUT);
  pinMode(MOTOR5_ENABLE_PIN, OUTPUT);
  pinMode(MOTOR6_ENABLE_PIN, OUTPUT);
  pinMode(MOTOR7_ENABLE_PIN, OUTPUT);

  digitalWrite(MOTOR1_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR2_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR3_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR4_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR5_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR6_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR7_ENABLE_PIN, HIGH);

  motor1.setMaxSpeed(MOTOR_MAX_STEPS_PER_SECOND);
  motor2.setMaxSpeed(MOTOR_MAX_STEPS_PER_SECOND);
  motor3.setMaxSpeed(MOTOR_MAX_STEPS_PER_SECOND);
  motor4.setMaxSpeed(MOTOR_MAX_STEPS_PER_SECOND);
  motor5.setMaxSpeed(MOTOR_MAX_STEPS_PER_SECOND);
  motor6.setMaxSpeed(MOTOR_MAX_STEPS_PER_SECOND);
  motor7.setMaxSpeed(MOTOR_MAX_STEPS_PER_SECOND);

  float accel = MOTOR_MAX_STEPS_PER_SECOND * 2.0f;
  motor1.setAcceleration(accel);
  motor2.setAcceleration(accel);
  motor3.setAcceleration(accel);
  motor4.setAcceleration(accel);
  motor5.setAcceleration(accel);
  motor6.setAcceleration(accel);
  motor7.setAcceleration(accel);

  FastLED.addLeds<WS2812B, DATA_PIN_LED1, GRB>(leds1, NUM_LEDS_LED1);
  FastLED.addLeds<WS2812B, DATA_PIN_LED2, GRB>(leds2, NUM_LEDS_LED2);
  FastLED.addLeds<WS2812B, DATA_PIN_LED3, GRB>(leds3, NUM_LEDS_LED3);
  FastLED.addLeds<WS2812B, DATA_PIN_LED4, GRB>(leds4, NUM_LEDS_LED4);
  FastLED.addLeds<WS2812B, DATA_PIN_LED5, GRB>(leds5, NUM_LEDS_LED5);

  FastLED.setBrightness(LED_GLOBAL_BRIGHTNESS);
  FastLED.clear();
  FastLED.show();

  last_led_update_ms = millis();
}

// ===================== Loop =====================
void loop() {
  const unsigned long now = millis();

  static String serialLine;
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialLine.startsWith("EMIX:")) {
        float solar, wind;
        if (parseEmixLine(serialLine, solar, wind)) {
          solar_energy_share = solar;
          wind_energy_share  = wind;
          //Serial.print("RX EMIX OK: solar=");
          //Serial.print(solar_energy_share, 3);
          //Serial.print(" wind=");
          //Serial.println(wind_energy_share, 3);
        } else {
          //Serial.print("RX EMIX FAIL: '");
          //Serial.print(serialLine);
          //Serial.println("'");
        }
      }
      serialLine = "";
    } else {
      if (serialLine.length() < 80) {
        serialLine += c;
      }
    }
  }

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

      

      if(now - tWindPrint >= PRINT_MS){
        tWindPrint = now;
        Serial.print(F("ADC="));    Serial.print(adc);
        Serial.print(F("  V(A1)=")); Serial.print(wind_v_ema,3); Serial.print(F(" V  "));
        Serial.println(spinning ? F("[SPINNING]") : F("[STOPPED]"));
      }
    }
  }

  updateMotorsFromRates();
  motor1.runSpeed();
  motor2.runSpeed();
  motor3.runSpeed();
  motor4.runSpeed();
  motor5.runSpeed();
  motor6.runSpeed();
  motor7.runSpeed();

  updateLedsFromRates();
}
