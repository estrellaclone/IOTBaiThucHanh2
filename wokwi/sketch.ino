#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ======================================================
// WIFI
// ======================================================

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// ======================================================
// THINGSBOARD
// ======================================================

const char* THINGSBOARD_SERVER = "mqtt.thingsboard.cloud";
const int THINGSBOARD_PORT = 1883;

// !!! THAY BANG ACCESS TOKEN CUA DEVICE !!!
const char* THINGSBOARD_TOKEN = "j6l4pzl1wu8ais21a34k";

const char* TELEMETRY_TOPIC = "v1/devices/me/telemetry";

// ======================================================
// DHT22
// ======================================================

#define DHT_PIN 15
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);

// ======================================================
// HC-SR04
// ======================================================

#define TRIG_PIN 5
#define ECHO_PIN 18

// ======================================================
// LCD 16x2 I2C
// ======================================================

#define LCD_ADDRESS 0x27

LiquidCrystal_I2C lcd(
  LCD_ADDRESS,
  16,
  2
);

// ======================================================
// MQTT
// ======================================================

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// ======================================================
// TIMER
// ======================================================

unsigned long lastTelemetry = 0;

const unsigned long TELEMETRY_INTERVAL = 2000;

// ======================================================
// LCD PAGE
// ======================================================

int lcdPage = 0;

// ======================================================
// WIFI
// ======================================================

void connectWiFi()
{
  Serial.println();
  Serial.println("========================================");
  Serial.println("Connecting to WiFi...");
  Serial.print("SSID: ");
  Serial.println(WIFI_SSID);

  WiFi.begin(
    WIFI_SSID,
    WIFI_PASSWORD,
    6
  );

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi connected!");

  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  Serial.print("RSSI: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");

  Serial.println("========================================");
}

// ======================================================
// THINGSBOARD
// ======================================================

void connectThingsBoard()
{
  while (!mqttClient.connected())
  {
    Serial.println();
    Serial.println("Connecting to ThingsBoard...");

    Serial.print("Server: ");
    Serial.println(THINGSBOARD_SERVER);

    if (mqttClient.connect(
          "ESP32_WOKWI",
          THINGSBOARD_TOKEN,
          ""
        ))
    {
      Serial.println("ThingsBoard MQTT connected!");
    }
    else
    {
      Serial.print("MQTT connection failed. State = ");
      Serial.println(mqttClient.state());

      Serial.println("Retrying in 3 seconds...");
      delay(3000);
    }
  }
}

// ======================================================
// HC-SR04
// ======================================================

float readDistance()
{
  digitalWrite(
    TRIG_PIN,
    LOW
  );

  delayMicroseconds(2);

  digitalWrite(
    TRIG_PIN,
    HIGH
  );

  delayMicroseconds(10);

  digitalWrite(
    TRIG_PIN,
    LOW
  );

  long duration = pulseIn(
    ECHO_PIN,
    HIGH,
    30000
  );

  if (duration == 0)
  {
    return -1;
  }

  float distance = duration / 58.0;

  return distance;
}

// ======================================================
// LCD - TEMPERATURE / HUMIDITY
// ======================================================

void displayTemperatureHumidity(
  float temperature,
  float humidity
)
{
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Temp: ");

  lcd.print(
    temperature,
    1
  );

  lcd.print((char)223);
  lcd.print("C");

  lcd.setCursor(0, 1);
  lcd.print("Hum : ");

  lcd.print(
    humidity,
    1
  );

  lcd.print("%");
}

// ======================================================
// LCD - DISTANCE
// ======================================================

void displayDistance(
  float distance
)
{
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Distance:");

  lcd.setCursor(0, 1);

  lcd.print(
    distance,
    1
  );

  lcd.print(" cm");
}

// ======================================================
// SEND TELEMETRY
// ======================================================

void sendTelemetry()
{
  // ----------------------------------------------------
  // READ DHT22
  // ----------------------------------------------------

  float temperature =
    dht.readTemperature();

  float humidity =
    dht.readHumidity();

  // ----------------------------------------------------
  // READ HC-SR04
  // ----------------------------------------------------

  float distance =
    readDistance();

  // ----------------------------------------------------
  // CHECK DHT22
  // ----------------------------------------------------

  if (
    isnan(temperature) ||
    isnan(humidity)
  )
  {
    Serial.println();
    Serial.println(
      "ERROR: Failed to read DHT22!"
    );

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("DHT22 ERROR!");

    return;
  }

  // ----------------------------------------------------
  // CHECK HC-SR04
  // ----------------------------------------------------

  if (distance < 0)
  {
    Serial.println();
    Serial.println(
      "ERROR: Failed to read HC-SR04!"
    );

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("HC-SR04 ERROR!");

    return;
  }

  // ----------------------------------------------------
  // SERIAL MONITOR
  // ----------------------------------------------------

  Serial.println();
  Serial.println(
    "========================================"
  );

  Serial.println(
    "          SENSOR DATA"
  );

  Serial.println(
    "========================================"
  );

  Serial.print(
    "Temperature : "
  );

  Serial.print(
    temperature,
    2
  );

  Serial.println(" C");

  Serial.print(
    "Humidity    : "
  );

  Serial.print(
    humidity,
    2
  );

  Serial.println(" %");

  Serial.print(
    "Distance    : "
  );

  Serial.print(
    distance,
    2
  );

  Serial.println(" cm");

  // ----------------------------------------------------
  // JSON
  // ----------------------------------------------------

  char payload[200];

  snprintf(
    payload,
    sizeof(payload),
    "{\"temperature\":%.2f,\"humidity\":%.2f,\"distance\":%.2f}",
    temperature,
    humidity,
    distance
  );

  Serial.println(
    "----------------------------------------"
  );

  Serial.print(
    "MQTT Topic  : "
  );

  Serial.println(
    TELEMETRY_TOPIC
  );

  Serial.print(
    "MQTT Payload: "
  );

  Serial.println(
    payload
  );

  // ----------------------------------------------------
  // SEND TO THINGSBOARD
  // ----------------------------------------------------

  bool success =
    mqttClient.publish(
      TELEMETRY_TOPIC,
      payload
    );

  Serial.println(
    "----------------------------------------"
  );

  if (success)
  {
    Serial.println(
      "STATUS      : Telemetry sent OK"
    );
  }
  else
  {
    Serial.println(
      "STATUS      : Telemetry FAILED"
    );
  }

  Serial.println(
    "========================================"
  );

  // ----------------------------------------------------
  // LCD
  // ----------------------------------------------------

  if (lcdPage == 0)
  {
    displayTemperatureHumidity(
      temperature,
      humidity
    );

    lcdPage = 1;
  }
  else
  {
    displayDistance(
      distance
    );

    lcdPage = 0;
  }
}

// ======================================================
// SETUP
// ======================================================

void setup()
{
  // ----------------------------------------------------
  // SERIAL
  // ----------------------------------------------------

  Serial.begin(115200);

  delay(1000);

  Serial.println();
  Serial.println();

  Serial.println(
    "########################################"
  );

  Serial.println(
    "#      ESP32 IoT WOKWI PROJECT         #"
  );

  Serial.println(
    "#                                      #"
  );

  Serial.println(
    "# DHT22 + HC-SR04 + LCD + ThingsBoard  #"
  );

  Serial.println(
    "########################################"
  );

  Serial.println();

  Serial.println(
    "System starting..."
  );

  // ----------------------------------------------------
  // DHT22
  // ----------------------------------------------------

  dht.begin();

  Serial.println(
    "DHT22 initialized."
  );

  // ----------------------------------------------------
  // HC-SR04
  // ----------------------------------------------------

  pinMode(
    TRIG_PIN,
    OUTPUT
  );

  pinMode(
    ECHO_PIN,
    INPUT
  );

  digitalWrite(
    TRIG_PIN,
    LOW
  );

  Serial.println(
    "HC-SR04 initialized."
  );

  // ----------------------------------------------------
  // LCD
  // ----------------------------------------------------

  Wire.begin(
    21,
    22
  );

  lcd.init();

  lcd.backlight();

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("ESP32 IoT");

  lcd.setCursor(0, 1);
  lcd.print("Starting...");

  Serial.println(
    "LCD initialized."
  );

  delay(2000);

  // ----------------------------------------------------
  // WIFI
  // ----------------------------------------------------

  connectWiFi();

  // ----------------------------------------------------
  // MQTT
  // ----------------------------------------------------

  mqttClient.setServer(
    THINGSBOARD_SERVER,
    THINGSBOARD_PORT
  );

  connectThingsBoard();

  // ----------------------------------------------------
  // READY
  // ----------------------------------------------------

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("System Ready");

  lcd.setCursor(0, 1);
  lcd.print("Interval: 2s");

  Serial.println();

  Serial.println(
    "System ready!"
  );

  Serial.println(
    "Reading interval: 2 seconds"
  );

  delay(2000);
}

// ======================================================
// LOOP
// ======================================================

void loop()
{
  // ----------------------------------------------------
  // WIFI
  // ----------------------------------------------------

  if (
    WiFi.status() != WL_CONNECTED
  )
  {
    Serial.println(
      "WiFi disconnected!"
    );

    connectWiFi();
  }

  // ----------------------------------------------------
  // MQTT
  // ----------------------------------------------------

  if (
    !mqttClient.connected()
  )
  {
    Serial.println(
      "MQTT disconnected!"
    );

    connectThingsBoard();
  }

  mqttClient.loop();

  // ----------------------------------------------------
  // READ EVERY 2 SECONDS
  // ----------------------------------------------------

  if (
    millis() - lastTelemetry
    >= TELEMETRY_INTERVAL
  )
  {
    lastTelemetry = millis();

    sendTelemetry();
  }
}