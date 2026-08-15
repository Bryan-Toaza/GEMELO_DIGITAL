"""
Controlador Webots Unificado y Autónomo - Gemelo Digital
Maneja: FSM, MQTT, OEE, MTTR, Latencia de Red, BDD y Reportes Gerenciales.
"""
from controller import Supervisor
import paho.mqtt.client as mqtt
import time
import json
import sqlite3
import os
import webbrowser
from datetime import datetime

# ==========================================
# CONFIGURACIÓN DE BASE DE DATOS
# ==========================================
db_path = "historial_oee.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS metricas_oee_sesiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        sim_time REAL,
        oee_global REAL,
        disponibilidad REAL,
        rendimiento REAL,
        calidad REAL,
        mttr REAL,
        fundas_producidas INTEGER
    )
''')
conn.commit()

# ==========================================
# CONFIGURACIÓN MQTT Y CINEMÁTICA
# ==========================================
MQTT_BROKER = "127.0.0.1"  
TIME_STEP = 32

POS_IZQ = 0.00           
POS_DER = -2.70          
POS_SELLADOR_IZQ = -0.79 
POS_SELLADOR_DER = 0.79  
POS_REPOSO = 0.0         
POS_TRAMPILLA_ABIERTA = -1.4
POS_TRAMPILLA_CERRADA = 0.0

TIEMPO_ESPERA_PRODUCTO = 2.0
TIEMPO_SELLADO = 2.0
TIEMPO_TRAMPILLA = 2.0
TIEMPO_CICLO_IDEAL = 1.86 + TIEMPO_ESPERA_PRODUCTO + TIEMPO_SELLADO + TIEMPO_TRAMPILLA 

# ==========================================
# INICIALIZACIÓN SUPERVISOR Y VARIABLES
# ==========================================
robot = Supervisor()
timestep = int(robot.getBasicTimeStep())

motor_dosi = robot.getDevice("Mov_dosi")
sellador_izq = robot.getDevice("Mov_sell_izq")
sellador_der = robot.getDevice("Mov_sell_der")
trampilla_izq = robot.getDevice("Soporte_Funda_mov2")
trampilla_der = robot.getDevice("Soporte_Funda_mov")

nodo_grupo_fundas = robot.getFromDef("GRUPO_FUNDAS")
campo_hijos = nodo_grupo_fundas.getField("children") if nodo_grupo_fundas else None

modo_operacion = "OFF"
emergencia_activa = False

# Variables de Sesión, OEE y MTTR
en_turno_produccion = False 
ciclo_automatico_corriendo = False
fase_detencion_solicitada = False

session_id = ""
hora_inicio_real = ""

numero_fundas = 5
meta_fundas = 5 
presion_objetivo = 30.0
lado_actual_ciclo = "DERECHA"

tiempo_planificado = 0.0      
tiempo_operativo = 0.0 
tiempo_total_fallos = 0.0
numero_fallos = 0

fundas_producidas_totales = 0 
ultima_actualizacion_oee = 0.0
ultimo_guardado_db = 0.0

# Variables de Red (Latencia)
latencia_ms = 0.0
ultimo_ping = 0.0

estado_actuadores = {
    "dosificador": False, "sellador_izq": False, "sellador_der": False,
    "trampilla_izq": False, "trampilla_der": False
}

class EstadoCiclo:
    REPOSO, MOVER_DOSIFICADOR, ESPERAR_LLEGADA, ESPERAR_PRODUCTO, SELLAR, ABRIR_TRAMPILLA, CONTAR_Y_CERRAR, FINALIZAR = range(8)

estado_ciclo = EstadoCiclo.REPOSO
tiempo_inicio_estado = 0.0

# ==========================================
# FUNCIONES AUXILIARES 
# ==========================================
def crear_funda_desde_codigo(lado):
    if not campo_hijos: return False
    y_pos = 1.0 if lado == "IZQUIERDA" else -1.0
    funda_vrml = f"""
    Solid {{
      translation 0.0 {y_pos} -10.0
      children [ DEF SHAPE_FUN Shape {{ appearance PBRAppearance {{ baseColor 0.8 0.2 0.2 roughness 0.8 metalness 0.1 }} geometry Box {{ size 0.8 0.8 0.8 }} }} ]
      name "funda_virtual_{int(robot.getTime() * 1000)}"
      boundingObject USE SHAPE_FUN physics Physics {{ density -1 mass 5.0 damping Damping {{ linear 0.8 angular 0.8 }} }}
    }}"""
    campo_hijos.importMFNodeFromString(-1, funda_vrml)
    return True

def mover_dosificador(estado):
    global estado_actuadores
    if motor_dosi: motor_dosi.setPosition(POS_DER if estado else POS_IZQ); estado_actuadores["dosificador"] = estado

def mover_sellador_izq(estado):
    global estado_actuadores
    if sellador_izq: sellador_izq.setPosition(POS_SELLADOR_IZQ if estado else POS_REPOSO); estado_actuadores["sellador_izq"] = estado

def mover_sellador_der(estado):
    global estado_actuadores
    if sellador_der: sellador_der.setPosition(POS_SELLADOR_DER if estado else POS_REPOSO); estado_actuadores["sellador_der"] = estado

def mover_trampilla_izq(estado):
    global estado_actuadores
    if trampilla_izq: trampilla_izq.setPosition(POS_TRAMPILLA_ABIERTA if estado else POS_TRAMPILLA_CERRADA); estado_actuadores["trampilla_izq"] = estado

def mover_trampilla_der(estado):
    global estado_actuadores
    if trampilla_der: trampilla_der.setPosition((-POS_TRAMPILLA_ABIERTA) if estado else POS_TRAMPILLA_CERRADA); estado_actuadores["trampilla_der"] = estado

def apagar_actuadores():
    mover_dosificador(False); mover_sellador_izq(False); mover_sellador_der(False); mover_trampilla_izq(False); mover_trampilla_der(False)

def actualizar_velocidad(presion):
    try:
        p = max(25.0, min(40.0, float(presion)))
        velocidad = 1.45 - ((p - 25.0) / 15.0) * 0.8
        if motor_dosi: motor_dosi.setVelocity(velocidad)
        return velocidad
    except: 
        return 1.45

velocidad_actual = actualizar_velocidad(30)

def procesar_toggle(llave, payload, funcion_mover):
    global estado_actuadores
    nuevo_estado = not estado_actuadores[llave] if payload == "TOGGLE" else (payload in ["1", "true"])
    funcion_mover(nuevo_estado)
    return nuevo_estado

# ==========================================
# CÁLCULO OEE Y REPORTE
# ==========================================
def calcular_y_publicar_oee(tiempo_actual):
    global tiempo_planificado, tiempo_operativo, fundas_producidas_totales, ultima_actualizacion_oee, ultimo_guardado_db
    global numero_fallos, tiempo_total_fallos, latencia_ms
    
    disponibilidad = 0.0
    rendimiento = 0.0
    calidad = 100.0 
    oee_global = 0.0
    mttr_actual = 0.0

    if tiempo_planificado > 0:
        disponibilidad = min(100.0, (tiempo_operativo / tiempo_planificado) * 100.0)
        if tiempo_operativo > 0:
            rendimiento = min(100.0, ((TIEMPO_CICLO_IDEAL * fundas_producidas_totales) / tiempo_operativo) * 100.0)
        oee_global = min(100.0, (disponibilidad / 100.0) * (rendimiento / 100.0) * (calidad / 100.0) * 100.0)
    
    if numero_fallos > 0:
        mttr_actual = tiempo_total_fallos / numero_fallos
        
    d_round, r_round, o_round, m_round = round(disponibilidad, 2), round(rendimiento, 2), round(oee_global, 2), round(mttr_actual, 2)
    
    if tiempo_actual - ultimo_guardado_db >= 2.0:
        if session_id != "":
            cursor.execute('''
                INSERT INTO metricas_oee_sesiones (session_id, sim_time, oee_global, disponibilidad, rendimiento, calidad, mttr, fundas_producidas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, tiempo_planificado, o_round, d_round, r_round, calidad, m_round, fundas_producidas_totales))
            conn.commit()
        ultimo_guardado_db = tiempo_actual

    datos_oee = {
        "disponibilidad": d_round, "rendimiento": r_round, "calidad": calidad,
        "oee_global": o_round, "fundas_producidas": fundas_producidas_totales,
        "tiempo_operativo_seg": round(tiempo_operativo, 2),
        "mttr_seg": m_round,
        "fallos_totales": numero_fallos,
        "latencia_ms": round(latencia_ms, 2)
    }
    cliente_mqtt.publish("metricas/oee", json.dumps(datos_oee))
    ultima_actualizacion_oee = tiempo_actual

def generar_reporte_html():
    if session_id == "":
        print("⚠️ [Webots] No hay sesión activa para generar reporte.")
        return

    print(f"📊 [Webots] Generando Reporte Gerencial para la sesión {session_id}...")
    hora_fin_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Extraer todos los datos para la gráfica
    cursor.execute('SELECT sim_time, oee_global, disponibilidad, rendimiento FROM metricas_oee_sesiones WHERE session_id = ? ORDER BY id ASC', (session_id,))
    registros = cursor.fetchall()
    
    # Extraer las estadísticas finales
    if registros:
        ultimo_reg = registros[-1]
        final_oee = ultimo_reg[1]
        final_disp = ultimo_reg[2]
        final_rend = ultimo_reg[3]
    else:
        final_oee = final_disp = final_rend = 0.0

    tiempo_op_min = round(tiempo_operativo / 60.0, 2)
    latencia_final = round(latencia_ms, 2)
    
    def format_sim_time(t):
        m = int(t // 60)
        s = int(t % 60)
        return f'"{m:02d}:{s:02d}"'
        
    etiquetas = [format_sim_time(r[0]) for r in registros] 
    datos_oee = [str(r[1]) for r in registros]
    datos_disp = [str(r[2]) for r in registros]
    datos_rend = [str(r[3]) for r in registros]
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Reporte y Métricas del Gemelo Digital</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 40px; }}
            .container {{ max-width: 1000px; margin: auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
            
            /* Encabezado */
            .header-reporte {{ text-align: center; margin-bottom: 40px; }}
            .header-reporte h1 {{ margin: 0; font-size: 28px; color: #111827; }}
            .header-reporte p {{ margin: 5px 0 0 0; color: #6b7280; font-size: 16px; font-weight: 500; }}
            
            /* Estructura Exigida (Separadores Negros) */
            h2.seccion-titulo {{
                color: #000;
                font-size: 20px;
                border-bottom: 2px solid #000;
                padding-bottom: 8px;
                margin-top: 35px;
                margin-bottom: 20px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}

            /* Cuadricula de Datos */
            .grid-kpis {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}
            .kpi-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; text-align: center; }}
            .kpi-card h4 {{ margin: 0 0 10px 0; color: #64748b; font-size: 13px; text-transform: uppercase; }}
            .kpi-card .valor {{ font-size: 26px; font-weight: 800; color: #0f172a; line-height: 1; }}
            .kpi-card .sub-valor {{ font-size: 14px; color: #475569; margin-top: 8px; display: block; }}

            /* Gráfica */
            .chart-container {{ position: relative; height: 50vh; width: 100%; margin-top: 10px; }}
            
            /* Observaciones sin fondo verde */
            .caja-observaciones {{
                background-color: transparent;
                border: 1px dashed #000;
                padding: 20px;
                min-height: 100px;
                border-radius: 4px;
            }}
            .caja-observaciones p {{ margin: 0; color: #64748b; font-style: italic; }}

            /* Botón inferior */
            .btn-imprimir {{ display: block; margin: 40px auto 0 auto; padding: 12px 25px; background-color: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; transition: all 0.3s; }}
            .btn-imprimir:hover {{ background-color: #1d4ed8; }}
            
            @media print {{ 
                .btn-imprimir {{ display: none; }} 
                body {{ background: white; padding: 0; }} 
                .container {{ box-shadow: none; max-width: 100%; padding: 0; }} 
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-reporte">
                <h1>Reporte y Métricas del Gemelo Digital</h1>
            </div>
            
            <h2 class="seccion-titulo">1. Información de la Sesión</h2>
            <div class="grid-kpis" style="grid-template-columns: 1fr 1fr;">
                <div class="kpi-card">
                    <h4>Identificador de Lote</h4>
                    <div class="valor" style="font-size: 18px; margin-top:10px;">{session_id}</div>
                </div>
                <div class="kpi-card">
                    <h4>Período de Ejecución</h4>
                    <span class="sub-valor" style="margin:0;"><strong>Inicio:</strong> {hora_inicio_real}</span>
                    <span class="sub-valor" style="margin:5px 0 0 0;"><strong>Fin:</strong> {hora_fin_real}</span>
                </div>
            </div>

            <h2 class="seccion-titulo">2. Tiempos y Operación</h2>
            <div class="grid-kpis">
                <div class="kpi-card">
                    <h4>Lote Total (Fundas)</h4>
                    <div class="valor">{fundas_producidas_totales}</div>
                </div>
                <div class="kpi-card">
                    <h4>Tiempo Operativo</h4>
                    <div class="valor">{tiempo_op_min} <small style="font-size: 14px; font-weight:600;">Minutos</small></div>
                </div>
                <div class="kpi-card">
                    <h4>Interrupciones / Paradas</h4>
                    <div class="valor">{numero_fallos}</div>
                </div>
            </div>

            <h2 class="seccion-titulo">3. Métricas de Producción (OEE Final)</h2>
            <div class="grid-kpis">
                <div class="kpi-card" style="border-bottom: 4px solid #10b981;">
                    <h4>OEE Global</h4>
                    <div class="valor">{final_oee}%</div>
                </div>
                <div class="kpi-card" style="border-bottom: 4px solid #3b82f6;">
                    <h4>Disponibilidad</h4>
                    <div class="valor">{final_disp}%</div>
                </div>
                <div class="kpi-card" style="border-bottom: 4px solid #ec4899;">
                    <h4>Rendimiento</h4>
                    <div class="valor">{final_rend}%</div>
                </div>
            </div>

            <h2 class="seccion-titulo">4. Desempeño de Red (MQTT)</h2>
            <div class="grid-kpis" style="grid-template-columns: 1fr;">
                <div class="kpi-card" style="display:flex; justify-content: space-between; align-items:center;">
                    <h4 style="margin:0;">Latencia Media Registrada:</h4>
                    <div class="valor" style="color: #64748b;">{latencia_final} ms</div>
                </div>
            </div>

            <h2 class="seccion-titulo">5. Análisis Gráfico de Tendencias</h2>
            <div class="chart-container">
                <canvas id="oeeChart"></canvas>
            </div>

            <button class="btn-imprimir" onclick="window.print()">🖨️ Guardar PDF / Imprimir</button>
        </div>
        
        <script>
            const ctx = document.getElementById('oeeChart').getContext('2d');
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: [{','.join(etiquetas)}],
                    datasets: [
                        {{ 
                            label: 'OEE Global (%)', 
                            data: [{','.join(datos_oee)}], 
                            borderColor: '#10b981', 
                            tension: 0.4, 
                            borderWidth: 3,
                            pointRadius: 0, 
                            pointHoverRadius: 6 
                        }},
                        {{ 
                            label: 'Disponibilidad (%)', 
                            data: [{','.join(datos_disp)}], 
                            borderColor: '#3b82f6', 
                            tension: 0.4, 
                            borderDash: [5, 5], 
                            borderWidth: 2,
                            pointRadius: 0, 
                            pointHoverRadius: 6 
                        }},
                        {{ 
                            label: 'Rendimiento (%)', 
                            data: [{','.join(datos_rend)}], 
                            borderColor: '#ec4899', 
                            tension: 0.4, 
                            borderDash: [5, 5], 
                            borderWidth: 2,
                            pointRadius: 0, 
                            pointHoverRadius: 6 
                        }}
                    ]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    interaction: {{ mode: 'index', intersect: false }},
                    plugins: {{
                        legend: {{ position: 'top', labels: {{ usePointStyle: true, padding: 20 }} }}
                    }},
                    scales: {{ 
                        y: {{ beginAtZero: true, max: 105 }},
                        x: {{ 
                            title: {{ display: true, text: 'Tiempo de Simulación (Min:Seg)' }},
                            ticks: {{ maxTicksLimit: 12, maxRotation: 45, minRotation: 45 }} 
                        }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """
    ruta_archivo = os.path.join(os.getcwd(), f"Reporte_OEE_{session_id}.html")
    with open(ruta_archivo, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ [Webots] Reporte guardado exitosamente en: {ruta_archivo}")
    
    try:
        webbrowser.open('file://' + os.path.realpath(ruta_archivo))
    except Exception as e:
        print(f"⚠️ [Webots] No se pudo abrir automáticamente el navegador: {e}")

# ==========================================
# CALLBACK MQTT
# ==========================================
def on_message(client, userdata, msg):
    global modo_operacion, emergencia_activa, ciclo_automatico_corriendo, en_turno_produccion
    global numero_fundas, meta_fundas, presion_objetivo, fase_detencion_solicitada, estado_ciclo, tiempo_inicio_estado, velocidad_actual
    global session_id, hora_inicio_real, tiempo_planificado, tiempo_operativo, fundas_producidas_totales, ultimo_guardado_db
    global numero_fallos, tiempo_total_fallos, latencia_ms
    
    tema = msg.topic.replace("maquina/simulacion/", "")
    payload = msg.payload.decode('utf-8').strip() 
    
    # Cálculo de latencia por Ping-Pong
    if tema == "sistema/ping":
        try:
            latencia_ms = (time.time() - float(payload)) * 1000.0
        except: pass
        return

    if tema == "panel/reporte" and payload == "1":
        generar_reporte_html()
        return

    if tema == "panel/selector" or tema == "modo_operacion": 
        modo_operacion = payload
        return
        
    if tema == "panel/emergencia":
        if payload == "1" and not emergencia_activa:
            numero_fallos += 1 
            
        emergencia_activa = (payload == "1")
        cliente_mqtt.publish("panel/led/emergencia", payload, retain=True)
        if emergencia_activa: 
            ciclo_automatico_corriendo = False
            apagar_actuadores()
        return

    if tema == "presion_objetivo" or tema == "sensor/presion": 
        presion_objetivo = float(payload)
        velocidad_actual = actualizar_velocidad(presion_objetivo)
        return
        
    if tema == "panel/display/set_fundas": 
        numero_fundas = int(payload)
        meta_fundas = numero_fundas  
        return

    if tema == "panel/auto/inicio" and payload == "1":
        if not emergencia_activa:
            cliente_mqtt.publish("panel/led/inicio", "1", retain=True)
            cliente_mqtt.publish("panel/led/detener", "0", retain=True)
            
            if not en_turno_produccion:
                session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                hora_inicio_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                tiempo_planificado = 0.0
                tiempo_operativo = 0.0
                fundas_producidas_totales = 0
                numero_fallos = 0
                tiempo_total_fallos = 0.0
                ultimo_guardado_db = robot.getTime()
                en_turno_produccion = True 

            if not ciclo_automatico_corriendo:
                ciclo_automatico_corriendo = True
                fase_detencion_solicitada = False
                estado_ciclo = EstadoCiclo.MOVER_DOSIFICADOR
                tiempo_inicio_estado = robot.getTime()
        return
        
    if tema == "panel/auto/paro" and payload == "1":
        cliente_mqtt.publish("panel/led/detener", "1", retain=True)
        cliente_mqtt.publish("panel/led/inicio", "0", retain=True)
        
        if ciclo_automatico_corriendo: 
            fase_detencion_solicitada = True
        else: 
            apagar_actuadores()
            if en_turno_produccion:
                en_turno_produccion = False
                generar_reporte_html()
        
        time.sleep(0.05)
        cliente_mqtt.publish("panel/led/detener", "0", retain=True)
        return
        
    componente = tema.split('/')[-1]
    actuadores_validos = ["dosificador", "pistondosificador", "sellador_izq", "pistonselladorizq", "sellador_der", "pistonselladorder", "trampilla_izq", "pistontrampillaizq", "trampilla_der", "pistontrampillader"]
    
    if componente in actuadores_validos:
        if emergencia_activa or ciclo_automatico_corriendo: 
            return
            
        if componente in ["dosificador", "pistondosificador"]: procesar_toggle("dosificador", payload, mover_dosificador)
        elif componente in ["sellador_izq", "pistonselladorizq"]: procesar_toggle("sellador_izq", payload, mover_sellador_izq)
        elif componente in ["sellador_der", "pistonselladorder"]: procesar_toggle("sellador_der", payload, mover_sellador_der)
        elif componente in ["trampilla_izq", "pistontrampillaizq"]:
            if procesar_toggle("trampilla_izq", payload, mover_trampilla_izq): crear_funda_desde_codigo("IZQUIERDA")
        elif componente in ["trampilla_der", "pistontrampillader"]:
            if procesar_toggle("trampilla_der", payload, mover_trampilla_der): crear_funda_desde_codigo("DERECHA")

# ==========================================
# LOOP PRINCIPAL
# ==========================================
cliente_mqtt = mqtt.Client(client_id="Webots_Supervisor_OEE_DB")
cliente_mqtt.on_message = on_message

try:
    cliente_mqtt.connect(MQTT_BROKER, 1883, 60)
    cliente_mqtt.subscribe("#") 
    cliente_mqtt.loop_start()
except Exception as e: print("❌ [Webots] Error de conexión:", e)

actualizar_velocidad(30)

while robot.step(timestep) != -1:
    tiempo_actual_simulacion = robot.getTime()
    tiempo_actual_real = time.time()
    
    if tiempo_actual_real - ultimo_ping >= 2.0:
        cliente_mqtt.publish("sistema/ping", str(tiempo_actual_real))
        ultimo_ping = tiempo_actual_real
    
    if en_turno_produccion:
        tiempo_planificado += (float(timestep) / 1000.0)
        if ciclo_automatico_corriendo and not emergencia_activa:
             tiempo_operativo += (float(timestep) / 1000.0)
             
    if emergencia_activa:
        tiempo_total_fallos += (float(timestep) / 1000.0)
    
    if tiempo_actual_simulacion - ultima_actualizacion_oee >= 1.0: 
        calcular_y_publicar_oee(tiempo_actual_simulacion)

    if emergencia_activa or not ciclo_automatico_corriendo: 
        continue
        
    if ciclo_automatico_corriendo:
        if numero_fundas <= 0:
            ciclo_automatico_corriendo = False
            en_turno_produccion = False
            estado_ciclo = EstadoCiclo.REPOSO
            apagar_actuadores()
            
            cliente_mqtt.publish("panel/led/detener", "1", retain=True)
            cliente_mqtt.publish("panel/led/inicio", "0", retain=True)
            time.sleep(0.05)
            cliente_mqtt.publish("panel/led/detener", "0", retain=True)
            
            generar_reporte_html()
            
            numero_fundas = meta_fundas
            cliente_mqtt.publish("sensor/conteo_actual", str(numero_fundas), retain=True)
            continue

        if estado_ciclo == EstadoCiclo.REPOSO:
            estado_ciclo = EstadoCiclo.MOVER_DOSIFICADOR
            tiempo_inicio_estado = tiempo_actual_simulacion

        elif estado_ciclo == EstadoCiclo.MOVER_DOSIFICADOR:
            mover_dosificador(lado_actual_ciclo == "DERECHA")
            estado_ciclo = EstadoCiclo.ESPERAR_LLEGADA
            tiempo_inicio_estado = tiempo_actual_simulacion

        elif estado_ciclo == EstadoCiclo.ESPERAR_LLEGADA:
            tiempo_viaje = 2.7 / max(0.1, velocidad_actual)
            if tiempo_actual_simulacion - tiempo_inicio_estado >= tiempo_viaje: 
                estado_ciclo = EstadoCiclo.ESPERAR_PRODUCTO
                tiempo_inicio_estado = tiempo_actual_simulacion

        elif estado_ciclo == EstadoCiclo.ESPERAR_PRODUCTO:
            if tiempo_actual_simulacion - tiempo_inicio_estado >= TIEMPO_ESPERA_PRODUCTO:
                estado_ciclo = EstadoCiclo.SELLAR; tiempo_inicio_estado = tiempo_actual_simulacion
                if lado_actual_ciclo == "DERECHA": mover_sellador_der(True)
                else: mover_sellador_izq(True)

        elif estado_ciclo == EstadoCiclo.SELLAR:
            if tiempo_actual_simulacion - tiempo_inicio_estado >= TIEMPO_SELLADO:
                apagar_actuadores() ; estado_ciclo = EstadoCiclo.ABRIR_TRAMPILLA; tiempo_inicio_estado = tiempo_actual_simulacion
                if lado_actual_ciclo == "DERECHA": mover_trampilla_der(True)
                else: mover_trampilla_izq(True)
                crear_funda_desde_codigo(lado_actual_ciclo)

        elif estado_ciclo == EstadoCiclo.ABRIR_TRAMPILLA:
            if tiempo_actual_simulacion - tiempo_inicio_estado >= TIEMPO_TRAMPILLA:
                apagar_actuadores(); estado_ciclo = EstadoCiclo.CONTAR_Y_CERRAR; tiempo_inicio_estado = tiempo_actual_simulacion

        elif estado_ciclo == EstadoCiclo.CONTAR_Y_CERRAR:
            numero_fundas -= 1; fundas_producidas_totales += 1
            cliente_mqtt.publish("sensor/conteo_actual", str(numero_fundas), retain=True)
            estado_ciclo = EstadoCiclo.FINALIZAR; tiempo_inicio_estado = tiempo_actual_simulacion

        elif estado_ciclo == EstadoCiclo.FINALIZAR:
            if fase_detencion_solicitada:
                ciclo_automatico_corriendo = False; fase_detencion_solicitada = False; estado_ciclo = EstadoCiclo.REPOSO
                en_turno_produccion = False
                generar_reporte_html()
            else:
                lado_actual_ciclo = "IZQUIERDA" if lado_actual_ciclo == "DERECHA" else "DERECHA"
                estado_ciclo = EstadoCiclo.REPOSO

# Cierre seguro
conn.close()
cliente_mqtt.loop_stop()
cliente_mqtt.disconnect()