#include <WiFi.h>
#include <PubSubClient.h>

// ============================================================
//  CONFIGURACIÓN DE RED
// ============================================================
const char* ssid = "docentes";
const char* password = "do2022asd*";
const char* mqtt_server = "172.20.19.73";

WiFiClient espClient;
PubSubClient client(espClient);

// ============================================================
//  ESTRUCTURA DE BOTONES CORREGIDA (DOBLE ESTADO)
// ============================================================
struct Boton {
  int pin;
  const char* topic;
  bool estadoLogico;       
  bool ultimoEstadoLeido;  
  unsigned long lastDebounceTime;
};

// Inicializamos todo en HIGH (No presionado)
Boton botones[] = {
  {15, "panel/prueba/motor", HIGH, HIGH, 0},       // ✅ MIGRADO: Del 16 al 15 (Reemplaza al LED de Emergencia)
  {0,  "panel/prueba/dosificador", HIGH, HIGH, 0}, 
  {18, "panel/prueba/sellador_izq", HIGH, HIGH, 0},
  {19, "panel/prueba/sellador_der", HIGH, HIGH, 0},
  {21, "panel/prueba/trampilla_izq", HIGH, HIGH, 0},
  {22, "panel/prueba/trampilla_der", HIGH, HIGH, 0},
  {23, "panel/display/mas", HIGH, HIGH, 0},
  {25, "panel/display/menos", HIGH, HIGH, 0},
  {26, "panel/boton/presion3", HIGH, HIGH, 0},
  {27, "panel/auto/inicio", HIGH, HIGH, 0},
  {32, "panel/auto/paro", HIGH, HIGH, 0},
  {33, "panel/emergencia", HIGH, HIGH, 0}
};
const int numBotones = 12;
const unsigned long DEBOUNCE_DELAY = 50;

// ============================================================
//  SELECTOR Y LEDS
// ============================================================
const int pinSelectorAuto = 13;     
const int pinSelectorManual = 14;   

bool lastAuto = HIGH;
bool lastManual = HIGH;
unsigned long lastSelectorChange = 0;
const unsigned long SELECTOR_DEBOUNCE = 100;  

// Indicadores visuales (Ánodo Común - Lógica Inversa)
// ¡El LED de emergencia fue retirado del hardware!
const int ledInicio = 5;       
const int ledDetener = 4;      
const int ledPresion3 = 2;     

unsigned long lastReconnectAttempt = 0;

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== HMI INICIADO (BOTÓN MOTOR EN PIN 15) ===");
  
  // Pines de Botones
  for (int i = 0; i < numBotones; i++) {
    pinMode(botones[i].pin, INPUT_PULLUP);
  }
  
  // Pines de Selector
  pinMode(pinSelectorAuto, INPUT_PULLUP);
  pinMode(pinSelectorManual, INPUT_PULLUP);

  // Pines de LEDs restantes
  pinMode(ledInicio, OUTPUT);
  pinMode(ledDetener, OUTPUT);
  pinMode(ledPresion3, OUTPUT);
  
  // Apagado inicial (HIGH apaga el LED en Ánodo Común)
  digitalWrite(ledInicio, HIGH);
  digitalWrite(ledDetener, HIGH);
  digitalWrite(ledPresion3, HIGH);

  conectarWiFi();
  
  client.setBufferSize(512);           
  client.setKeepAlive(60);             
  client.setServer(mqtt_server, 1883);
  client.setCallback(recepcionLeds);
  
  delay(500);
  publicarEstadoSelector();
}

// ============================================================
//  LOOP PRINCIPAL
// ============================================================
void loop() {
  unsigned long currentMillis = millis();

  // --- 1. SUPERVISOR DE RED ---
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ Router desconectó el WiFi. Reconectando...");
    WiFi.disconnect();
    WiFi.reconnect();
    delay(1000);
    return; 
  }

  if (!client.connected()) {
    if (currentMillis - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = currentMillis;
      reconectarMQTT_NoBloqueante();
    }
    return; 
  } else {
    client.loop(); 
  }

  // --- 2. LECTURA DE BOTONES ---
  for (int i = 0; i < numBotones; i++) {
    bool lecturaActual = digitalRead(botones[i].pin);
    
    if (lecturaActual != botones[i].ultimoEstadoLeido) {
      botones[i].lastDebounceTime = currentMillis; 
    }
    
    if ((currentMillis - botones[i].lastDebounceTime) > DEBOUNCE_DELAY) {
      if (lecturaActual != botones[i].estadoLogico) {
        botones[i].estadoLogico = lecturaActual; 
        
        if (botones[i].estadoLogico == LOW) { // Fue Presionado
          if (String(botones[i].topic).startsWith("panel/prueba/")) {
            client.publish(botones[i].topic, "TOGGLE");
          } else {
            client.publish(botones[i].topic, "1");
          }
          Serial.printf("[HMI] ✅ PRESIONADO: %s\n", botones[i].topic);
        } 
        else { // Fue Soltado
          if (!String(botones[i].topic).startsWith("panel/prueba/")) {
            client.publish(botones[i].topic, "0");
          }
        }
      }
    }
    botones[i].ultimoEstadoLeido = lecturaActual;
  }

  // --- 3. LECTURA DE SELECTOR ---
  bool currentAuto = digitalRead(pinSelectorAuto);
  bool currentManual = digitalRead(pinSelectorManual);

  if ((currentAuto != lastAuto || currentManual != lastManual) && 
      (currentMillis - lastSelectorChange > SELECTOR_DEBOUNCE)) {
    lastSelectorChange = currentMillis;
    publicarEstadoSelector();
    lastAuto = currentAuto;
    lastManual = currentManual;
  }
}

// ============================================================
//  FUNCIONES AUXILIARES
// ============================================================
void publicarEstadoSelector() {
  bool autoState = digitalRead(pinSelectorAuto);
  bool manualState = digitalRead(pinSelectorManual);
  
  if (autoState == LOW && manualState == HIGH) {
    client.publish("panel/selector", "AUTO");
    Serial.println("[HMI] 🟢 SELECTOR: AUTOMÁTICO");
  } else if (manualState == LOW && autoState == HIGH) {
    client.publish("panel/selector", "MANUAL");
    Serial.println("[HMI] 🟡 SELECTOR: MANUAL (PRUEBAS)");
  } else {
    client.publish("panel/selector", "OFF");
    Serial.println("[HMI] 🔴 SELECTOR: APAGADO");
  }
}

void recepcionLeds(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  String ruta = String(topic);

  // Ánodo Común: msg == "1" enviamos LOW (Enciende). Si no, HIGH (Apaga).
  if (ruta == "panel/led/inicio") {
    digitalWrite(ledInicio, msg == "1" ? LOW : HIGH);
  } else if (ruta == "panel/led/detener") {
    digitalWrite(ledDetener, msg == "1" ? LOW : HIGH);
  } else if (ruta == "panel/led/presion3") {
    digitalWrite(ledPresion3, msg == "1" ? LOW : HIGH);
  }
}

void conectarWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("Conectando WiFi");
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 40) {
    delay(500); Serial.print("."); intentos++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi Conectado (HMI)");
  } else {
    Serial.println("\n❌ Conexión WiFi fallida. Reiniciando placa...");
    delay(3000);
    ESP.restart();
  }
}

bool reconectarMQTT_NoBloqueante() {
  Serial.print("Conectando MQTT en HMI...");
  if (client.connect("ESP32_Observador")) {
    Serial.println("✅ OK");
    client.subscribe("panel/led/#");
    return true;
  }
  Serial.printf(" falló, rc=%d\n", client.state());
  return false;
}