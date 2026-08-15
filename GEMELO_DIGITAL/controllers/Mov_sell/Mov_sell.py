"""Controlador Webots - Selladores"""
from controller import Robot
import paho.mqtt.client as mqtt

MQTT_BROKER = "127.0.0.1" # o tu IP "172.20.19.73"
POS_IZQ_ACTIVA = -0.79
POS_DER_ACTIVA = 0.79
POS_REPOSO = 0.0

robot = Robot()
timestep = int(robot.getBasicTimeStep())
sellador_izq = robot.getDevice("Mov_sell_izq")
sellador_der = robot.getDevice("Mov_sell_der")

estado_izq = False
estado_der = False

def mover_izq(estado):
    if sellador_izq: sellador_izq.setPosition(POS_IZQ_ACTIVA if estado else POS_REPOSO)

def mover_der(estado):
    if sellador_der: sellador_der.setPosition(POS_DER_ACTIVA if estado else POS_REPOSO)

def al_recibir_mensaje(client, userdata, msg):
    global estado_izq, estado_der
    tema = msg.topic
    payload = msg.payload.decode('utf-8')

    # Toggles desde HMI Físico
    if tema == "panel/prueba/sellador_izq":
        estado_izq = not estado_izq
        mover_izq(estado_izq)
    elif tema == "panel/prueba/sellador_der":
        estado_der = not estado_der
        mover_der(estado_der)

    # Comandos Node-RED (Izquierdo)
    elif tema in ["actuador/pistonselladorizq", "maquina/simulacion/pistonselladorizq", "maquina/real/pistonselladorizq"]:
        estado_izq = (payload == "1")
        mover_izq(estado_izq)

    # Comandos Node-RED (Derecho)
    elif tema in ["actuador/pistonselladorder", "maquina/simulacion/pistonselladorder", "maquina/real/pistonselladorder"]:
        estado_der = (payload == "1")
        mover_der(estado_der)

cliente_mqtt = mqtt.Client(client_id="Webots_Selladores")
cliente_mqtt.on_message = al_recibir_mensaje

try:
    cliente_mqtt.connect(MQTT_BROKER, 1883, 60)
    cliente_mqtt.subscribe("panel/prueba/sellador_izq")
    cliente_mqtt.subscribe("panel/prueba/sellador_der")
    cliente_mqtt.subscribe("maquina/simulacion/#")
    cliente_mqtt.subscribe("maquina/real/#")
    cliente_mqtt.subscribe("actuador/#")
    cliente_mqtt.loop_start()
except Exception as e:
    print("Error MQTT Selladores:", e)

while robot.step(timestep) != -1:
    pass

cliente_mqtt.loop_stop()
cliente_mqtt.disconnect()