#include <WiFi.h>
#include <PubSubClient.h>
#include <TM1637Display.h>
#include <ESP32Servo.h>

const char* ssid = "docentes";
const char* password = "do2022asd*";
const char* mqtt_server = "172.20.19.73";

// ============================================================
//  MAPEO DE PINES PERFECTO (EJECUTOR)
// ============================================================
// LAS 11 SALIDAS EXACTAS (100% Seguras y puras, cero parpadeos)
const int pinMaestro = 13;
const int pinMotor   = 14;
const int valvulaTrampillaIzq = 18;   //18
const int valvulaTrampillaDer = 19;   //19
#define PIN_SERVO 21
#define CLK 22
#define DIO 23
const int valvulaDosificador = 25;   //25
const int valvulaSelladorIzq = 26;   //26
const int valvulaSelladorDer = 27;   //27
#define PIN_ULTRA_TRIG 4

TM1637Display display(CLK, DIO);
Servo servoPresion;

// LAS 6 ENTRADAS (Sensores. Mapeo a pines de Entrada Segura / ADC)
#define PIN_IR_CONTADOR   32  // Usa INPUT_PULLUP interno
#define PIN_IR_DOSIF_DER  33  // Usa INPUT_PULLUP interno
#define PIN_ULTRA_ECHO    34  // Input-Only puro
#define PIN_IR_DOSIF_IZQ  35  // Input-Only puro
#define PIN_ADC_TEMP      36  // VP - Excelente para analógico
#define PIN_ADC_PRESION   39  // VN - Excelente para analógico

// --- VARIABLES DE PROCESO ---
int numeroFundas = 5;
int presionTarget = 30;       
bool modoConfigPresion = false;

String modoOperacion = "OFF";
bool automaticoCorriendo = false;
bool faseDetencionSolicitada = false;
bool primeraDeteccionOmitida = false;

bool estadoMotor = false; bool estadoDosificador = false;
bool estadoSelladorIzq = false; bool estadoSelladorDer = false;
bool estadoTrampillaIzq = false; bool estadoTrampillaDer = false;
bool cicloPruebaActivo = false;

unsigned long tiempoBaseDosif = 4000;
unsigned long tiempoBaseSella = 3000;

unsigned long lastMqttMessage = 0;
const unsigned long MQTT_WATCHDOG_MS = 15000;  
unsigned long lastSensorPublish = 0;
const unsigned long SENSOR_PUBLISH_MS = 2000;
unsigned long ultimoMuestreoSensores = 0;

float nivelTolvaGlobal = 0.0;
float psiGlobal = 0.0;
float tempGlobal = 0.0;
bool emergenciaActiva = false;
unsigned long lastReconnectAttempt = 0;

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {
  Serial.begin(115200);
  delay(1500); 
  Serial.println("\n=== EJECUTOR INICIADO (LÓGICA MANUAL CORREGIDA) ===");
  
  pinMode(pinMaestro, OUTPUT); pinMode(pinMotor, OUTPUT);
  pinMode(valvulaDosificador, OUTPUT); pinMode(valvulaSelladorIzq, OUTPUT);
  pinMode(valvulaSelladorDer, OUTPUT); pinMode(valvulaTrampillaIzq, OUTPUT);
  pinMode(valvulaTrampillaDer, OUTPUT); pinMode(PIN_ULTRA_TRIG, OUTPUT);
  apagarSalidasFisicas();

  // Entradas protegidas
  pinMode(PIN_IR_CONTADOR, INPUT_PULLUP);
  pinMode(PIN_IR_DOSIF_DER, INPUT_PULLUP);
  // Los pines 34, 35, 36, 39 son input por defecto y no soportan pull-up.
  pinMode(PIN_ULTRA_ECHO, INPUT);
  pinMode(PIN_IR_DOSIF_IZQ, INPUT); 

  servoPresion.attach(PIN_SERVO);
  actualizarPosicionServo();
  display.setBrightness(0x0f);
  actualizarVisualizacionDisplay();

  conectarWiFi();
  client.setBufferSize(512);
  client.setKeepAlive(60);
  client.setServer(mqtt_server, 1883);
  client.setCallback(recepcionHmi);
  publicarEstadoInicial();
}

void loop() {
  if (!client.connected()) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > 5000) { lastReconnectAttempt = now; if (reconectarMQTT_NoBloqueante()) lastReconnectAttempt = 0; }
  } else { client.loop(); }

  if (emergenciaActiva) { delay(20); return; }

  // Modificado para que aplique también al ciclo manual
  if (millis() - lastMqttMessage > MQTT_WATCHDOG_MS && (automaticoCorriendo || cicloPruebaActivo)) {
    publicarDebug("⚠️ WATCHDOG: Enlace MQTT perdido. Abortando por seguridad."); abortarSistemaInmediatamente();
  }

  // Muestreo a 4 Hz para no congelar el procesador
  if (millis() - ultimoMuestreoSensores > 250) {
    ultimoMuestreoSensores = millis();
    nivelTolvaGlobal = leerPorcentajeTolva();
    psiGlobal = leerTransductorPresion();
    tempGlobal = leerTemperatura();
  }

  if (automaticoCorriendo && modoOperacion == "AUTO") {
    if (nivelTolvaGlobal <= 10.0) { publicarDebug("ERROR: Tolva < 10%."); abortarSistemaInmediatamente(); return; }
    ejecutarMaquinaEstadosAutomatica();
  }

  // ✅ NUEVA UBICACIÓN: Llamado constante de la rutina manual sin bloquear WiFi
  if (cicloPruebaActivo && modoOperacion == "MANUAL") {
    ejecutarCicloPrueba();
  }

  if (millis() - lastSensorPublish > SENSOR_PUBLISH_MS) {
    lastSensorPublish = millis(); publicarSensores(nivelTolvaGlobal, psiGlobal, tempGlobal);
  }
}

void ejecutarMaquinaEstadosAutomatica() {
  long aumentoTiempo = (presionTarget > 25) ? ((presionTarget - 25) / 3) * 1000 : 0;
  unsigned long tiempoDosifAdaptado = tiempoBaseDosif + aumentoTiempo;
  unsigned long tiempoSellaAdaptado = tiempoBaseSella + aumentoTiempo;

  bool irIzq = digitalRead(PIN_IR_DOSIF_IZQ) == LOW; 
  bool irDer = digitalRead(PIN_IR_DOSIF_DER) == LOW;

  if (irIzq || irDer) {
    if (!primeraDeteccionOmitida) { primeraDeteccionOmitida = true; delay(500); return; }

    if (irIzq) {
      digitalWrite(valvulaDosificador, LOW); esperarSincronizado(tiempoDosifAdaptado); digitalWrite(valvulaDosificador, HIGH);
      if(emergenciaActiva) return;
      digitalWrite(valvulaSelladorIzq, LOW); esperarSincronizado(tiempoSellaAdaptado); digitalWrite(valvulaSelladorIzq, HIGH);
    } else if (irDer) {
      digitalWrite(valvulaDosificador, LOW); esperarSincronizado(tiempoDosifAdaptado); digitalWrite(valvulaDosificador, HIGH);
      if(emergenciaActiva) return;
      digitalWrite(valvulaSelladorDer, LOW); esperarSincronizado(tiempoSellaAdaptado); digitalWrite(valvulaSelladorDer, HIGH);
    }
    if(emergenciaActiva) return;
    digitalWrite(valvulaTrampillaIzq, LOW); digitalWrite(valvulaTrampillaDer, LOW);
    esperarSincronizado(1500);
    digitalWrite(valvulaTrampillaIzq, HIGH); digitalWrite(valvulaTrampillaDer, HIGH);

    numeroFundas--; if (!modoConfigPresion) actualizarVisualizacionDisplay();
    client.publish("sensor/conteo_actual", String(numeroFundas).c_str());

    if (numeroFundas <= 0 || faseDetencionSolicitada) { abortarSistemaInmediatamente(); }
  }
}

// ============================================================
//  NUEVO CICLO DE PRUEBA (MANUAL INTELIGENTE)
// ============================================================
void ejecutarCicloPrueba() {

    delay(500);
      digitalWrite(valvulaDosificador, LOW);
      esperarSincronizado(6000); // Esperar 5s 
      digitalWrite(valvulaDosificador, HIGH); // Apagar dosificador
      if(emergenciaActiva) return;
      
      digitalWrite(valvulaSelladorDer, LOW);
      esperarSincronizado(4000); // Esperar 4s
      digitalWrite(valvulaSelladorDer, HIGH);
      if(emergenciaActiva) return;
      
      digitalWrite(valvulaTrampillaDer, LOW); // Lado cruzado
      esperarSincronizado(3000); // Esperar 3s
      digitalWrite(valvulaTrampillaDer, HIGH);
      
      numeroFundas--;
      if (!modoConfigPresion) actualizarVisualizacionDisplay();
      client.publish("sensor/conteo_actual", String(numeroFundas).c_str());
      esperarSincronizado(1000); // Pausa breve óptica

      //Aquí hice un cambio      
      digitalWrite(valvulaSelladorIzq, LOW);
      esperarSincronizado(4000); // Esperar 4s
      digitalWrite(valvulaSelladorIzq, HIGH);
      if(emergenciaActiva) return;
      
      digitalWrite(valvulaTrampillaIzq, LOW); // Lado cruzado
      esperarSincronizado(3000); // Esperar 3s
      digitalWrite(valvulaTrampillaIzq, HIGH);
      
      numeroFundas--;
      if (!modoConfigPresion) actualizarVisualizacionDisplay();
      client.publish("sensor/conteo_actual", String(numeroFundas).c_str());
      esperarSincronizado(1000); // Pausa breve óptica
    

    // Evaluación de fin de lote
    if (numeroFundas <= 0 || faseDetencionSolicitada) {
      cicloPruebaActivo = false;
      faseDetencionSolicitada = false;
      client.publish("panel/led/inicio", "0");
      // digitalWrite(pinMotor, HIGH); // El motor se desactiva al finalizar el conteo de fundas
    }
}

void recepcionHmi(char* topic, byte* payload, unsigned int length) {
  lastMqttMessage = millis(); String msg = ""; for (int i = 0; i < length; i++) msg += (char)payload[i]; String ruta = String(topic);
  
  if (ruta == "panel/selector") {
    modoOperacion = msg;
    if (modoOperacion == "AUTO" || modoOperacion == "MANUAL") digitalWrite(pinMaestro, LOW); 
    else abortarSistemaInmediatamente();
    return;
  }
  if (ruta == "panel/emergencia" && msg == "1") { emergenciaActiva = true; cicloPruebaActivo = false; client.publish("panel/led/emergencia", "1"); abortarSistemaInmediatamente(); return; }
  if (ruta == "panel/emergencia" && msg == "0") { emergenciaActiva = false; client.publish("panel/led/emergencia", "0"); return; }

  if (ruta == "panel/display/mas" && msg == "1") {
    if (modoConfigPresion) { presionTarget = constrain(presionTarget + 1, 25, 40); actualizarPosicionServo(); } else if (!automaticoCorriendo && !cicloPruebaActivo) numeroFundas += 1;
    actualizarVisualizacionDisplay(); return;
  }
  if (ruta == "panel/display/menos" && msg == "1") {
    if (modoConfigPresion) { presionTarget = constrain(presionTarget - 1, 25, 40); actualizarPosicionServo(); } else if (!automaticoCorriendo && !cicloPruebaActivo && numeroFundas > 1) numeroFundas -= 1;
    actualizarVisualizacionDisplay(); return;
  }
  if (ruta == "panel/boton/presion3" && msg == "1") { modoConfigPresion = !modoConfigPresion; actualizarVisualizacionDisplay(); client.publish("panel/led/presion3", modoConfigPresion ? "1" : "0"); return; }
  
  if (ruta == "panel/auto/inicio" && msg == "1") {
    if (emergenciaActiva) return;
    
    // ✅ INICIO SECUENCIA MANUAL
    if (modoOperacion == "MANUAL" && !cicloPruebaActivo && numeroFundas > 0) {
      cicloPruebaActivo = true;
      faseDetencionSolicitada = false;
      primeraDeteccionOmitida = false;
      client.publish("panel/led/inicio", "1");
      // digitalWrite(pinMotor, LOW); // El motor inicia al dar inicio
      return;
    }
    
    // INICIO SECUENCIA AUTOMÁTICA
    if (modoOperacion == "AUTO" && !automaticoCorriendo && nivelTolvaGlobal > 10.0) {
      automaticoCorriendo = true; faseDetencionSolicitada = false; primeraDeteccionOmitida = false;
      digitalWrite(pinMotor, LOW); client.publish("panel/led/inicio", "1"); client.publish("panel/led/detener", "0");
    }
    return;
  }
  
  if (ruta == "panel/auto/paro" && msg == "1") {
    if (automaticoCorriendo || cicloPruebaActivo) { // Aplica a ambos modos
      faseDetencionSolicitada = true;
      client.publish("panel/led/detener", "1");
    } else {
      apagarSalidasFisicas(); client.publish("panel/led/detener", "1"); client.publish("panel/led/inicio", "0"); delay(100); client.publish("panel/led/detener", "0"); 
    }
    return;
  }

  if (modoOperacion == "MANUAL" && ruta.startsWith("panel/prueba/")) {
    if (emergenciaActiva) return;
    bool* estadoPtr = nullptr; int pin = -1;
    if (ruta.endsWith("motor")) { estadoPtr = &estadoMotor; pin = pinMotor; }
    else if (ruta.endsWith("dosificador")) { estadoPtr = &estadoDosificador; pin = valvulaDosificador; }
    else if (ruta.endsWith("sellador_izq")) { estadoPtr = &estadoSelladorIzq; pin = valvulaSelladorIzq; }
    else if (ruta.endsWith("sellador_der")) { estadoPtr = &estadoSelladorDer; pin = valvulaSelladorDer; }
    else if (ruta.endsWith("trampilla_izq")) { estadoPtr = &estadoTrampillaIzq; pin = valvulaTrampillaIzq; }
    else if (ruta.endsWith("trampilla_der")) { estadoPtr = &estadoTrampillaDer; pin = valvulaTrampillaDer; }
    if (estadoPtr != nullptr && pin != -1) { *estadoPtr = !(*estadoPtr); digitalWrite(pin, *estadoPtr ? LOW : HIGH); }
    return;
  }

  if (ruta == "actuador/pistonmotor") { estadoMotor = (msg == "1"); digitalWrite(pinMotor, estadoMotor ? LOW : HIGH); }
  if (ruta == "actuador/pistondosificador") { estadoDosificador = (msg == "1"); digitalWrite(valvulaDosificador, estadoDosificador ? LOW : HIGH); }
  if (ruta == "actuador/pistonselladorizq") { estadoSelladorIzq = (msg == "1"); digitalWrite(valvulaSelladorIzq, estadoSelladorIzq ? LOW : HIGH); }
  if (ruta == "actuador/pistonselladorder") { estadoSelladorDer = (msg == "1"); digitalWrite(valvulaSelladorDer, estadoSelladorDer ? LOW : HIGH); }
  if (ruta == "actuador/pistontrampillaizq") { estadoTrampillaIzq = (msg == "1"); digitalWrite(valvulaTrampillaIzq, estadoTrampillaIzq ? LOW : HIGH); }
  if (ruta == "actuador/pistontrampillader") { estadoTrampillaDer = (msg == "1"); digitalWrite(valvulaTrampillaDer, estadoTrampillaDer ? LOW : HIGH); }
  if (ruta == "presion_objetivo") { presionTarget = constrain(msg.toInt(), 25, 40); actualizarPosicionServo(); }
}

void publicarSensores(float nivelTolva, float psiActual, float tempActual) {
  client.publish("sensor/ultra", String(nivelTolva, 1).c_str()); client.publish("sensor/presion", String(psiActual, 2).c_str());
  client.publish("sensor/temp", String(tempActual, 1).c_str()); client.publish("sensor/conteo_actual", String(numeroFundas).c_str());
  client.publish("sensor/ir1", digitalRead(PIN_IR_CONTADOR) ? "0" : "1"); client.publish("sensor/ir2", digitalRead(PIN_IR_DOSIF_IZQ) ? "0" : "1");
  client.publish("sensor/ir3", digitalRead(PIN_IR_DOSIF_DER) ? "0" : "1");
}

void publicarEstadoInicial() { client.publish("panel/led/inicio", "0"); client.publish("panel/led/detener", "0"); client.publish("panel/led/presion3", "0"); }
void actualizarVisualizacionDisplay() { if (modoConfigPresion) display.showNumberDec(presionTarget); else display.showNumberDec(numeroFundas); }
void actualizarPosicionServo() { servoPresion.write(constrain(map(presionTarget, 25, 40, 0, 180), 0, 180)); }

float leerPorcentajeTolva() {
  digitalWrite(PIN_ULTRA_TRIG, LOW); delayMicroseconds(2); digitalWrite(PIN_ULTRA_TRIG, HIGH); delayMicroseconds(10); digitalWrite(PIN_ULTRA_TRIG, LOW);
  long duracion = pulseIn(PIN_ULTRA_ECHO, HIGH, 25000); if (duracion == 0) return 0.0;
  return constrain(100.0 - ((((duracion / 2.0) / 29.1) / 80.0) * 100.0), 0.0, 100.0);
}

float leerTransductorPresion() { return ((analogRead(PIN_ADC_PRESION) / 4095.0) * 3.3 / 3.3) * 232.06; }
float leerTemperatura() { return (analogRead(PIN_ADC_TEMP) / 4095.0) * 3.3 / 0.01; }
void esperarSincronizado(unsigned long ms) { unsigned long t_inicio = millis(); while (millis() - t_inicio < ms) { client.loop(); if (emergenciaActiva) break; delay(5); } }

void apagarSalidasFisicas() { 
  digitalWrite(pinMaestro, HIGH); digitalWrite(pinMotor, HIGH); digitalWrite(valvulaDosificador, HIGH); 
  digitalWrite(valvulaSelladorIzq, HIGH); digitalWrite(valvulaSelladorDer, HIGH); 
  digitalWrite(valvulaTrampillaIzq, HIGH); digitalWrite(valvulaTrampillaDer, HIGH); 
}

void abortarSistemaInmediatamente() {
  automaticoCorriendo = false; faseDetencionSolicitada = false; cicloPruebaActivo = false; apagarSalidasFisicas();
  estadoMotor = false; estadoDosificador = false; estadoSelladorIzq = false; estadoSelladorDer = false; estadoTrampillaIzq = false; estadoTrampillaDer = false;
  client.publish("panel/led/inicio", "0"); client.publish("panel/led/detener", "0");
  // digitalWrite(pinMotor, HIGH); // Apagado de emergencia del motor
}

void publicarDebug(String mensaje) { Serial.println("[DEBUG]: " + mensaje); client.publish("dashboard/debug", mensaje.c_str()); }
void conectarWiFi() { WiFi.mode(WIFI_STA); WiFi.begin(ssid, password); int intentos = 0; while (WiFi.status() != WL_CONNECTED && intentos < 40) { delay(500); intentos++; } if (WiFi.status() != WL_CONNECTED) ESP.restart(); }
bool reconectarMQTT_NoBloqueante() { if (client.connect("ESP32_Ejecutor")) { client.subscribe("panel/selector"); client.subscribe("panel/display/#"); client.subscribe("panel/boton/presion3"); client.subscribe("panel/auto/#"); client.subscribe("panel/emergencia"); client.subscribe("panel/prueba/#"); client.subscribe("actuador/#"); client.subscribe("presion_objetivo"); client.subscribe("modo_operacion"); client.subscribe("ciclo_produccion"); publicarEstadoInicial(); return true; } return false; }