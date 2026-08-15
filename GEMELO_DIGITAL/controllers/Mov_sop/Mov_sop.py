"""
Controlador Webots Autónomo - Soporte y Trampillas de Funda (Supervisor)
Sincroniza ciclos manuales virtuales, velocidad por presión, parada de emergencia
y simulación física de caída de objetos sin requerir la presencia del ESP32.
"""
from controller import Supervisor
import paho.mqtt.client as mqtt

# ==========================================
# CONFIGURACIÓN CINEMÁTICA Y RED
# ==========================================
MQTT_BROKER = "127.0.0.1"  # Modifica a tu IP "172.20.19.73" si usas broker externo
TIME_STEP = 32

POS_ABIERTA = -1.4  
POS_CERRADA = 0.0

# Inicialización del nodo como Supervisor Industrial
robot = Supervisor()
timestep = int(robot.getBasicTimeStep())

# Vinculación de Actuadores Lineales
trampilla_izq = robot.getDevice("Soporte_Funda_mov2")
trampilla_der = robot.getDevice("Soporte_Funda_mov")

# Variables de Estado de Red y Proceso
entorno_trabajo = "simulacion"
emergencia_activa = False
ciclo_virtual_corriendo = False
numero_fundas_virtuales = 5
presion_virtual_psi = 30.0
lado_actual_ciclo = "DERECHO"  # Ajustado a DERECHO / IZQUIERDO para match estricto

# ==========================================
# GESTIÓN DE OBJETOS 3D (SUPERVISOR)
# ==========================================
nodo_funda = robot.getFromDef("FUNDA_SIMULADA") 
campo_traduccion = None
if nodo_funda:
    campo_traduccion = nodo_funda.getField("translation")

def simular_caida_funda(lado):
    """Resetea la posición del objeto 3D sobre la trampilla abierta para que caiga por gravedad"""
    if campo_traduccion:
        x_pos = -0.3 if lado == "IZQUIERDO" else 0.3
        campo_traduccion.setSFVec3f([x_pos, 0.8, -0.1]) 
        nodo_funda.resetPhysics() 
        print(f"📦 [Webots] Funda {lado} generada y liberada por gravedad.")

# ==========================================
# FUNCIONES DE MOVIMIENTO MECÁNICO
# ==========================================
def mover_izq(estado):
    if trampilla_izq: 
        trampilla_izq.setPosition(POS_ABIERTA if estado else POS_CERRADA)

def mover_der(estado):
    if trampilla_der: 
        trampilla_der.setPosition((-POS_ABIERTA) if estado else POS_CERRADA)

def aplicar_parada_total_virtual():
    mover_izq(False)
    mover_der(False)

# ==========================================
# ORQUESTACIÓN DE EVENTOS MQTT
# ==========================================
def on_message(client, userdata, msg):
    global entorno_trabajo, emergencia_activa, ciclo_virtual_corriendo
    global numero_fundas_virtuales, presion_virtual_psi, lado_actual_ciclo
    
    tema = msg.topic
    payload = msg.payload.decode('utf-8')

    # 1. Detectar el entorno de trabajo seleccionado en Node-RED
    if tema == "modo_operacion":
        entorno_trabajo = payload
        return

    # 2. Escucha de la Presión (Soporta ruta limpia y ruta con prefijo del Enrutador)
    if tema in ["presion_objetivo", "maquina/simulacion/presion_objetivo"]:
        presion_virtual_psi = float(payload)
        print(f"💨 [Webots] Registro de presión actualizado en simulación: {presion_virtual_psi} PSI")
        return

    # 3. Gestión de la Parada de Emergencia Virtual (Soporta ruta con prefijo)
    if tema in ["panel/emergencia", "maquina/simulacion/panel/emergencia"]:
        if payload == "1":
            emergencia_activa = True
            ciclo_virtual_corriendo = False
            aplicar_parada_total_virtual()
            print("🚨 [Webots] PARADA DE EMERGENCIA VIRTUAL ACTIVADA. Secuencia abortada.")
        else:
            emergencia_activa = False
            print("✅ [Webots] Emergencia virtual rearmada.")
        return

    # 4. Captura del lote de fundas enviadas desde Node-RED
    if tema in ["panel/display/set_fundas", "maquina/simulacion/panel/display/set_fundas"]:
        numero_fundas_virtuales = int(payload)
        print(f"🔢 [Webots] Lote de simulación fijado en: {numero_fundas_virtuales} fundas.")
        return

    # 5. Interceptación de comandos de Inicio / Paro de Lote Virtual (Soporta rutas con prefijo)
    if tema in ["panel/auto/inicio", "maquina/simulacion/panel/auto/inicio"] and payload == "1":
        if not emergencia_activa and not ciclo_virtual_corriendo:
            ciclo_virtual_corriendo = True
            lado_actual_ciclo = "DERECHO" 
            print(f"▶️ [Webots] Secuencia batch virtual iniciada: {numero_fundas_virtuales} fundas.")
        return

    if tema in ["panel/auto/paro", "maquina/simulacion/panel/auto/paro"] and payload == "1":
        ciclo_virtual_corriendo = False
        aplicar_parada_total_virtual()
        print("⏹️ [Webots] Lote virtual detenido por operador.")
        return

    # 6. Comandos unitarios directos (Toggles manuales de Node-RED)
    if tema in ["actuador/pistontrampillaizq", "maquina/simulacion/pistontrampillaizq"]:
        if not emergencia_activa:
            mover_izq(payload == "1")
            if payload == "1": simular_caida_funda("IZQUIERDO")

    elif tema in ["actuador/pistontrampillader", "maquina/simulacion/pistontrampillader"]:
        if not emergencia_activa:
            mover_der(payload == "1")
            if payload == "1": simular_caida_funda("DERECHO")

# ==========================================
# BUCLE DE EJECUCIÓN (FSM AUTÓNOMA)
# ==========================================
cliente_mqtt = mqtt.Client(client_id="Webots_Trampillas_Supervisor")
cliente_mqtt.on_message = on_message

try:
    cliente_mqtt.connect(MQTT_BROKER, 1883, 60)
    cliente_mqtt.subscribe("modo_operacion")
    cliente_mqtt.subscribe("panel/emergencia")
    cliente_mqtt.subscribe("panel/display/set_fundas")
    cliente_mqtt.subscribe("panel/auto/#")
    cliente_mqtt.subscribe("presion_objetivo")
    cliente_mqtt.subscribe("maquina/simulacion/#")
    cliente_mqtt.subscribe("actuador/#")
    cliente_mqtt.loop_start()
except Exception as e:
    print("Error crítico de red en Supervisor Webots:", e)

cronometro_estado = 0.0
fase_secuencia = "REPOSO"

while robot.step(TIME_STEP) != -1:
    if emergencia_activa or not ciclo_virtual_corriendo:
        fase_secuencia = "REPOSO"
        continue

    tiempo_actual = robot.getTime()

    if fase_secuencia == "REPOSO" and ciclo_virtual_corriendo:
        if numero_fundas_virtuales > 0:
            fase_secuencia = "DOSIFICANDO"
            cronometro_estado = tiempo_actual
            # ✅ CORRECCIÓN: Envía cadenas idénticas al filtro que lee tu controlador_dosificador.py
            print(f"⏳ [Webots] Procesando funda virtual. Restantes: {numero_fundas_virtuales}")
            cliente_mqtt.publish("dashboard/debug", f"Lado {lado_actual_ciclo} detectado. Dosificando...")
        else:
            ciclo_virtual_corriendo = False
            print("📦 [Webots] Lote de fundas virtual terminado con éxito.")

    elif fase_secuencia == "DOSIFICANDO":
        if tiempo_actual - cronometro_estado >= 5.0:
            fase_secuencia = "SELLANDO"
            cronometro_estado = tiempo_actual
            cliente_mqtt.publish("dashboard/debug", f"Sellador {lado_actual_ciclo.capitalize()} ON")

    elif fase_secuencia == "SELLANDO":
        if tiempo_actual - cronometro_estado >= 4.0:
            fase_secuencia = "DESCARGANDO"
            cronometro_estado = tiempo_actual
            
            # Apertura física sincronizada y desove del objeto 3D
            if lado_actual_ciclo == "DERECHO":
                mover_izq(True) 
                simular_caida_funda("IZQUIERDO")
            else:
                mover_der(True)
                simular_caida_funda("DERECHO")

    elif fase_secuencia == "DESCARGANDO":
        if tiempo_actual - cronometro_estado >= 3.0:
            mover_izq(False)
            mover_der(False)
            
            numero_fundas_virtuales -= 1
            # Publica tanto al tópico nativo del visor HTML como al debug general
            cliente_mqtt.publish("sensor/conteo_actual", str(numero_fundas_virtuales))
            cliente_mqtt.publish("dashboard/debug", f"Funda terminada. Restantes: {numero_fundas_virtuales}")
            
            lado_actual_ciclo = "IZQUIERDO" if lado_actual_ciclo == "DERECHO" else "DERECHO"
            fase_secuencia = "REPOSO"

cliente_mqtt.loop_stop()
cliente_mqtt.disconnect()