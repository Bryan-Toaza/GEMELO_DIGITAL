import os
import sys
import base64
import json
import requests
from openai import OpenAI
import PyPDF2
import re
from datetime import datetime

# ============================================
# 1. VALIDACIÓN DE API KEYS
# ============================================
if "DEEPSEEK_API_KEY" not in os.environ:
    print("\n" + "="*60)
    print("[ERROR] No se detectó la variable de entorno DEEPSEEK_API_KEY.")
    print("="*60)
    print("\n📌 CÓMO CONFIGURARLA EN WINDOWS:")
    print("   1. Abre PowerShell como Administrador")
    print("   2. Ejecuta: [System.Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY','tu-api-key-aqui','User')")
    print("   3. Cierra y vuelve a abrir VS Code")
    print("="*60 + "\n")
    sys.exit(1)

# Opcional: Brave Search API para búsqueda web (recomendado)
BRAVE_API_KEY = os.environ.get('BRAVE_API_KEY', None)
if BRAVE_API_KEY:
    print("✅ Brave Search API detectada")
else:
    print("⚠️  Brave Search API no configurada. La búsqueda web usará modo limitado.")
    print("   Obtén una API Key gratis en: https://brave.com/search/api/")

# ============================================
# 2. INICIALIZAR CLIENTE DE DEEPSEEK
# ============================================
cliente = OpenAI(
    api_key=os.environ.get('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com"
)

# ============================================
# 3. CONFIGURACIÓN DEL PROYECTO
# ============================================
CARPETA_BORRADORES = "Borradores"
CARPETA_VERIFICACION = "Verificacion_Citas"

# ============================================
# 3.1 CONTEXTO COMPLETO DE LA TESIS (TODOS LOS CAPÍTULOS)
# ============================================

CONTEXTO_CAPITULOS = """

=========================================
CAPÍTULO 1: INTRODUCCIÓN
=========================================

\chapter{Introducción}
\label{chap:introduccion}

\section{Contextualización}

La globalización de las cadenas de suministro agroindustriales ha generado una presión sin precedentes sobre los sistemas de manufactura y procesamiento de alimentos. En la última década, la Industria 4.0 ha emergido como un paradigma transformador que fusiona activos físicos con tecnologías digitales para crear sistemas ciberfísicos. En este contexto, la República del Ecuador presenta un escenario dual: mientras el sector agroindustrial representa un pilar fundamental de su Producto Interno Bruto (PIB), la tasa de adopción de tecnologías habilitadoras de la Cuarta Revolución Industrial en las Pequeñas y Medianas Empresas (PYMES) y centros de investigación de la región latinoamericana aún se encuentra en una fase de maduración temprana.

El presente proyecto de investigación se origina en el Laboratorio de Procesos de la Universidad Indoamérica, donde opera una máquina dosificadora de granos considerada un activo de alto valor educativo. Esta máquina es una representante típica de la maquinaria legacy industrial: opera mediante un circuito de potencia a 220V, controlado por un PLC de arquitectura cerrada, que gobierna una secuencia de relés y electroválvulas neumáticas para ejecutar el ciclo de dosificación. La arquitectura cerrada impuesta por el fabricante y las políticas de mantenimiento institucionales impidieron cualquier manipulación, condenando a este recurso a funcionar como una "caja negra".

Ante esta limitación, se diseñó una integración ciberfísica no invasiva mediante un sistema de bypass externo gobernado por microcontroladores ESP32, que permite capturar las señales críticas del proceso sin alterar el cableado interno del PLC. A través de esta arquitectura, se replica digitalmente el comportamiento completo de la máquina, habilitando un entorno de simulación y validación que respeta la integridad del sistema original.

\section{Estado del Arte}

En la esfera de la manufactura inteligente, el concepto de Gemelo Digital ha evolucionado desde la mera gestión del ciclo de vida del producto hasta convertirse en un habilitador crítico para la simulación predictiva. Tao et al. establecieron una taxonomía de madurez que clasifica los gemelos en varios niveles, desde el monitoreo (Nivel 1) hasta la autonomía prescriptiva (Nivel 4). Para esta investigación, el foco se sitúa en el Nivel 3 (Predictivo/Interactivo), donde el modelo virtual no solo recibe datos en tiempo real, sino que puede interactuar con el sistema físico para anticipar fallos.

La naturaleza secuencial de las máquinas dosificadoras convierte a la teoría de control de eventos discretos en un área de estudio fundamental. Cassandras y Lafortune formalizaron el uso de las Máquinas de Estados Finitos como un modelo determinístico ideal para sistemas industriales que transitan entre estados excluyentes. Su implementación en Python dentro de entornos de simulación 3D como Webots representa un avance significativo frente a los simuladores puramente matemáticos.

El Internet Industrial de las Cosas ofrece la columna vertebral comunicacional para estos sistemas. El protocolo MQTT se destaca por su modelo de publicación/suscripción ligero, ideal para la telemetría bidireccional entre el ESP32 y el panel de control. A nivel de supervisión, Node-RED ha desplazado en entornos académicos a los SCADA propietarios tradicionales debido a su flexibilidad y capacidad de integración visual.

A partir de la revisión sistemática presentada, se identifica una brecha de investigación significativa en la integración de Gemelos Digitales de Nivel 3 para maquinaria electromecánica heredada que carece de puertos de comunicación modernos. La literatura actual está dominada por trabajos que asumen conectividad nativa o capacidad de modificación total del hardware, condición que rara vez se cumple en los laboratorios universitarios y las PYMES agroindustriales ecuatorianas.

\section{Planteamiento del Problema}

La máquina dosificadora de granos ubicada en el Laboratorio de Procesos de la Universidad Indoamérica representa un quebranto tecnológico para el desarrollo académico de la institución. A pesar de ser completamente funcional, su arquitectura de control presenta serias limitaciones para la investigación en Industria 4.0. El sistema opera bajo una filosofía de control de lazo cerrado y opaco: un PLC propietario enclavado a un contactor trifásico de 220V ejecuta la lógica de electroválvulas y pistones en un ciclo estrictamente secuencial.

La situación problemática se define por tres causas raíz: (1) la política de no manipulación interna del equipo, (2) la naturaleza legacy del equipo que implica ausencia total de buses de comunicación industrial modernos, y (3) las restricciones presupuestarias del laboratorio. Los efectos se traducen en tiempos de inactividad no programados, pérdida de trazabilidad, e imposibilidad de desarrollar prácticas orientadas a la transformación digital.

Surge la pregunta de investigación: ¿Cómo diseñar e implementar un gemelo digital predictivo e interactivo para una máquina dosificadora de granos, sin modificar su estructura interna de control, mediante un bypass ciberfísico que garantice la interoperabilidad con tecnologías IIoT?

\section{Justificación}

El desarrollo se justifica desde cuatro perspectivas. En el ámbito técnico, la solución introduce el concepto de bypass ciberfísico como alternativa no invasiva para la modernización industrial. Desde el punto de vista operativo, la migración hacia un gemelo digital predictivo busca minimizar las mermas y las interrupciones del servicio. La justificación académica radica en la capacidad de transferencia del conocimiento generado como caso de estudio replicable. Finalmente, la viabilidad económica se sustenta en tecnologías de bajo costo y amplia disponibilidad en el mercado local.

\section{Objetivos}

\subsection{Objetivo General}

Desarrollar un gemelo digital interactivo y predictivo de una máquina dosificadora de granos mediante la integración del motor de simulación Webots, una arquitectura de Máquina de Estados Finitos (FSM) y un bypass ciberfísico basado en ESP32, para emular fielmente la cinemática del ciclo industrial y habilitar la validación algorítmica de métricas de rendimiento y resiliencia ante escenarios de falla en un entorno ciberfísico seguro.

\subsection{Objetivos Específicos}

1. Levantar y diagnosticar la lógica secuencial y los parámetros operativos de la dosificadora electromecánica y su controlador base, definiendo la topología de la red de información, los tiempos de latencia del sistema físico y los puntos críticos de instrumentación para la integración ciberfísica.

2. Diseñar e implementar el modelo ciberfísico en Webots, programando una FSM en Python que gobierne de manera aislada la cinemática de los actuadores (alimentación, dosificación y sellado), integrando la telemetría mediante el protocolo MQTT y el panel SCADA en Node-RED, y ejecutando el bypass que respete la integridad del sistema original.

3. Evaluar la resiliencia y eficiencia de la lógica de control mediante la inyección de perturbaciones virtuales (fallos de presión y lectura), cuantificando el impacto en el rendimiento operativo, la capacidad de detección de anomalías y la efectividad general del sistema frente a escenarios de falla simulados.

\section{Alcance del Proyecto}

El proyecto se circunscribe al diseño, desarrollo y validación de un Sistema Ciberfísico de Nivel 3 (Gemelo Predictivo e Interactivo), enfocado exclusivamente en la réplica digital de la maquinaria y su analítica operativa.

En el alcance incluido, el proyecto abarca: (1) Modelado Cinemático 3D en Webots, (2) Arquitectura Lógica de Control con FSM en Python, (3) Capa de Comunicaciones y SCADA con MQTT y Node-RED, (4) Extracción Analítica de métricas de rendimiento, y (5) Bypass Ciberfísico no intrusivo.

En el alcance excluido, esta investigación no contempla: (1) desarrollo de modelos de Inteligencia Artificial para recomendaciones autónomas (Nivel 4), (2) sistemas de inspección visual, (3) despliegue en infraestructuras de Cloud Computing, y (4) optimización de la máquina física original.

\section{Fundamentación Teórica}

Un Gemelo Digital es una representación virtual integral de un activo físico que se actualiza de manera continua mediante flujos de datos, permitiendo simular, predecir y optimizar su comportamiento. La evolución de esta tecnología se categoriza en 5 niveles de madurez. La investigación se enfoca en el Nivel 3 (Predictivo/Interactivo), que establece una comunicación bidireccional para simular y anticipar comportamientos.

Las FSM proporcionan el modelo matemático ideal para el control secuencial de procesos de manufactura con estados excluyentes. La capa de instrumentalización externa se sustenta en el microcontrolador ESP32-WROOM. La conectividad IIoT se resuelve mediante MQTT, y la supervisión con Node-RED.

El concepto de Bypass Ciberfísico es la innovación metodológica central, diseñada para superar la barrera de la arquitectura cerrada del PLC, mediante captura pasiva de señales e inyección lógica de comandos vía relés externos.


=========================================
CAPÍTULO 2: METODOLOGÍA
=========================================

\chapter{Metodología}
\label{chap:metodologia}

\section{Diagnóstico de la Situación Actual}

El punto de partida es una máquina dosificadora de granos de arquitectura electromecánica heredada, que opera como una "caja negra". Su funcionamiento original se basa en un circuito de potencia a 220V controlado por un PLC sin interfaces de red. Para caracterizar este funcionamiento se aplicaron técnicas de ingeniería inversa con multímetros y trazados de continuidad.

Las limitaciones más críticas fueron: (1) imposibilidad de modificar el cableado interno, (2) falta de registro de estados discretos, y (3) nula visibilidad de variables de proceso. Ante estas restricciones se diseñó una integración ciberfísica mediante un bypass no intrusivo con ESP32.

\section{Metodología de Desarrollo e Implementación}

Se adoptó el modelo en V (V-Model) adaptado a sistemas ciberfísicos. Las fases de ingeniería son: (1) Definición Arquitectónica según ISO 23247, (2) Diseño de Subsistemas en Webots y Node-RED, (3) Implementación Física del panel IP54, (4) Verificación mediante Virtual Commissioning, y (5) Validación del Sistema con métricas EMO.

\section{Técnicas e Instrumentos de Recolección de Información}

La caracterización de la máquina legacy se sustentó en observación directa estructurada y análisis de señales eléctricas. El controlador de la FSM en Webots genera registros automáticos en CSV. La arquitectura MQTT usa tópicos maquina/sensor/# y maquina/actuador/# con frecuencia de muestreo de 100 ms.

\section{Configuración e Implementación de Equipos}

Los ESP32 fueron configurados con sensores en GPIO específicos. El broker Mosquitto se desplegó en Linux con puertos 1883 y 9001. Node-RED se configuró con nodos MQTT, Dashboard y SQLite. Webots se seleccionó por su integración con Python y bajo consumo de CPU.

\section{Requerimientos del Sistema}

Los requerimientos funcionales incluyen: Control Híbrido y Bypass, Enclavamiento de Seguridad, Fidelidad Cinemática en 3D, Secuestro de Señales, Telemetría en Tiempo Real, y Datalogging Automatizado. Los no funcionales incluyen latencia <100 ms, inmunidad EMI, eficiencia computacional, disponibilidad >99.9%, y escalabilidad.

\section{Diseño de la Solución}

El diseño de hardware incluye optoacopladores PC817, fuente switching 12V/10A, y panel IP54. El diseño de red define tópicos MQTT con payloads JSON. El diseño cinemático en Webots usa nodos SliderJoint y HingeJoint. El ciclo de vida de la comunicación fluye desde ESP32 → MQTT → Node-RED → Webots.

\section{Justificación Técnica y Adaptación de Métricas}

Se justifica la selección de ESP32, MQTT, Webots y Node-RED. La métrica EMO adapta el OEE eliminando el factor de calidad: EMO (%) = Disponibilidad × Rendimiento × 100. El MTTR se calcula como la suma de tiempos de inactividad dividido por el número de fallos.

\section{Presupuesto y Recursos Económicos}

La inversión total fue de $243.20 USD, detallada en tabla de componentes.


=========================================
CAPÍTULO 3: IMPLEMENTACIÓN, PRUEBAS Y RESULTADOS
=========================================

\chapter{Implementación, Pruebas y Resultados}
\label{chap:implementacion}

\section{Descripción de la Solución Implementada}

La arquitectura final materializa un CPS de nivel 3 con bypass ciberfísico paralelo. La caja de control IP54 alberga dos ESP32, sensores (infrarrojos, ultrasónico, presión), y actuadores (relés 8 canales, servomotor). El bypass utiliza optoacopladores PC817 para aislamiento galvánico.

\section{Proceso de Implementación}

El desarrollo se estructuró en siete fases iterativas, incluyendo diseño del panel, programación de firmware, configuración MQTT, desarrollo SCADA, modelado 3D en FreeCAD, programación FSM en Webots, y pruebas de validación.

\section{Pruebas y Validación}

Se realizaron cinco pruebas con lotes de 60 a 200 fundas. La Prueba 1 (200 fundas) alcanzó OEE 92.33%. La Prueba 5 con fallo inyectado registró OEE 84.62% y MTTR de 52 segundos.

\section{Análisis de Resultados}

El OEE promedio fue 91.85% con σ = ±0.46%. La latencia MQTT promedio fue 0.61 ms. La prueba 5 validó la propagación de señales de anomalía y la ejecución de protocolo de recuperación.

\section{Comparativa con la Situación Inicial}

La implementación transformó la máquina de una "caja negra" a un sistema con monitorización en tiempo real, mantenimiento predictivo (Nivel 3), OEE medible (91.85%), detección de fallos, MTTR cuantificado (52 segundos), y trazabilidad de producción.

\section{Cumplimiento de Objetivos}

Se confirma el cumplimiento del Objetivo General y los tres objetivos específicos: levantamiento y diagnóstico, diseño e implementación, y evaluación mediante pruebas de validación.

\section{Análisis de Desempeño de Red MQTT}

La latencia media fue 0.61 ms, cumpliendo holgadamente el requisito de <100 ms. Se trabajó con QoS 1 sin pérdidas de paquetes. Los microcontroladores no experimentaron reinicios durante 76.11 minutos de operación bajo carga inductiva.

\section{Discusión de Resultados}

Los resultados posicionan al prototipo por encima del umbral estándar de eficacia. La consistencia en la desviación estándar sugiere fidelidad del modelo cinemático. Se reconocen limitaciones como la exclusión del factor Calidad en OEE y pruebas en entorno controlado.

\section{Cronograma y Presupuesto Ejecutado}

El cronograma se ajustó en 85% a la planificación. El costo ejecutado fue $243.20 USD, sin desviaciones significativas, utilizando exclusivamente herramientas de código abierto.


=========================================
CAPÍTULO 4: CONCLUSIONES Y RECOMENDACIONES
=========================================

\chapter{Conclusiones y Recomendaciones}
\label{chap:conclusiones}

\section{Conclusiones}

Se demostró empíricamente la viabilidad de implementar un Gemelo Digital de Nivel 3 en una máquina legacy mediante bypass ciberfísico no intrusivo. Se alcanzó OEE promedio de 91.85% con σ = ±0.46%. La capacidad predictiva se validó en la Prueba 5 con MTTR de 52 segundos.

Se cumplieron los tres objetivos específicos: (1) levantamiento y diagnóstico mediante ingeniería inversa, (2) diseño e implementación completa de la arquitectura, y (3) evaluación con métricas cuantitativas robustas.

Las principales aportaciones son: (1) metodología de bypass ciberfísico no intrusivo, (2) arquitectura de integración vertical de bajo costo, y (3) caso de estudio replicable para entornos académicos.

Las limitaciones incluyen: (1) OEE sin factor de Calidad por ausencia de sistema de pesaje, (2) pruebas en entorno controlado de laboratorio, (3) fallo inyectado solo en escenario neumático, y (4) curva de aprendizaje en Webots que extendió el cronograma 3 días.

\section{Recomendaciones}

Para el Laboratorio de Procesos: incorporar el gemelo digital como módulo didáctico transversal y establecer protocolo de mantenimiento predictivo. Para la Universidad: crear laboratorio especializado en Gemelos Digitales y gestionar alianzas con el sector agroindustrial. Para el sector: considerar la monitorización OEE como primer paso para Mejora Continua. Técnicamente: incorporar factor de Calidad con celda de carga y desarrollar aplicación móvil.

\section{Trabajos Futuros}

Se propone la evolución a Nivel 4 (Prescriptivo) con algoritmos de IA. Nuevas líneas incluyen aplicación de la metodología en otras máquinas legacy, integración de Realidad Aumentada, y Blockchain para trazabilidad. También se propone investigar Edge Computing para control de lazo cerrado ultra-rápido.


=========================================
CAPÍTULO 5: RESULTADOS CLAVE DEL PROYECTO
=========================================

RESULTADOS CUANTITATIVOS OBTENIDOS:

- OEE Global promedio (4 pruebas sin fallos): 91.85% con σ = ±0.46%
- Disponibilidad: 100% en condiciones normales
- Rendimiento promedio: 91.85%
- Latencia MQTT promedio: 0.61 ms (requisito: < 100 ms)
- MTTR ante fallo inyectado: 52 segundos
- Disponibilidad durante fallo: 92.92%
- Presupuesto ejecutado: $243.20 USD
- Tiempo total de pruebas: 76.11 minutos acumulados

METODOLOGÍA UTILIZADA:
- V-Model adaptado a sistemas ciberfísicos
- Prácticas de eXtreme Programming (XP) para desarrollo de software
- TDD (Test-Driven Development)
- Integración Continua (CI)

TECNOLOGÍAS IMPLEMENTADAS:
- Hardware: 2 ESP32, sensores infrarrojos, ultrasónico, transductor de presión, módulo relés 8 canales, servomotor, display TM1637, fuente 12V/10A
- Software: Webots, Node-RED, FreeCAD, Mosquitto MQTT
- Protocolos: MQTT, I2C, WiFi
- Lenguajes: Python (FSM), JSON (payloads)

ARQUITECTURA DEL SISTEMA:
- Bypass ciberfísico no intrusivo
- Comunicación bidireccional ESP32 ↔ MQTT ↔ Node-RED ↔ Webots
- Máquina de Estados Finitos (FSM) en Python
- SCADA en Node-RED con dashboard OEE
- Modelado 3D en FreeCAD y Webots

HECHOS INMUTABLES DEL PROYECTO:
1. Ubicación: Laboratorio de Procesos de la Universidad Indoamérica
2. Máquina legacy con PLC y circuito 220V
3. Sin permisos para manipulación completa
4. Dos ESP32 como controladores externos
5. Bypass con optoacopladores PC817
6. Simulación en Webots (descartando Nvidia Isaac Sim)
7. FSM en Python
8. Node-RED para SCADA y Mosquitto MQTT

"""

# ============================================
# 3.2 INSTRUCCIONES DEL AGENTE
# ============================================

INSTRUCCIONES_AGENTE = """
Eres un agente académico de nivel maestría, experto en Ingeniería en Tecnologías de la Información y Sistemas Ciberfísicos.

Tu función es generar el ABSTRACT y el RESUMEN EJECUTIVO de la tesis descrita en el CONTEXTO COMPLETO DE CAPÍTULOS que se te proporciona.

REGLAS ESTRICTAS:

1. **ABSTRACT EN ESPAÑOL (250-300 palabras):**
   - Debe incluir: contexto del problema, objetivo general, metodología empleada, resultados cuantitativos clave, conclusiones principales.
   - Formato: texto corrido, sin viñetas, sin citas bibliográficas.
   - Nivel académico: maestría, lenguaje formal y preciso.
   - Palabras clave: 5 palabras clave al final del abstract.

2. **ABSTRACT EN INGLÉS (250-300 palabras):**
   - Traducción fiel del abstract en español.
   - Debe mantener el mismo contenido y nivel académico.
   - Keywords: 5 keywords al final.

3. **RESUMEN EJECUTIVO EN ESPAÑOL (500-600 palabras):**
   - Debe ser más extenso que el abstract.
   - Estructura: problema, objetivos, metodología detallada, resultados cuantitativos, limitaciones, impacto y recomendaciones.
   - Formato: texto corrido, con párrafos temáticos claros.
   - Nivel ejecutivo: debe ser comprensible para un lector no especializado.

4. **RESUMEN EJECUTIVO EN INGLÉS (500-600 palabras):**
   - Traducción fiel del resumen ejecutivo en español.
   - Mismo nivel de detalle y estructura.

5. **FORMATO DE SALIDA:**
   - El agente debe entregar el contenido en un único archivo .tex con la siguiente estructura:

\\chapter*{Resumen}
\\addcontentsline{toc}{chapter}{Resumen}
[Contenido del Abstract en español]

\\chapter*{Abstract}
\\addcontentsline{toc}{chapter}{Abstract}
[Contenido del Abstract en inglés]

\\chapter*{Resumen Ejecutivo}
\\addcontentsline{toc}{chapter}{Resumen Ejecutivo}
[Contenido del Resumen Ejecutivo en español]

\\chapter*{Executive Summary}
\\addcontentsline{toc}{chapter}{Executive Summary}
[Contenido del Resumen Ejecutivo en inglés]

6. **PALABRAS CLAVE / KEYWORDS:**
   - Español: Gemelo Digital, Sistema Ciberfísico, Bypass Ciberfísico, Máquina de Estados Finitos, Industria 4.0
   - Inglés: Digital Twin, Cyber-Physical System, Cyber-Physical Bypass, Finite State Machine, Industry 4.0

7. **NO INCLUIR CITAS BIBLIOGRÁFICAS** en el abstract ni en el resumen ejecutivo.

8. **LENGUAJE:** Formal, académico, claro y preciso.

9. **NO ALUCINAR:** Toda la información debe estar basada exclusivamente en el CONTEXTO COMPLETO DE CAPÍTULOS proporcionado.

"""

# ============================================
# 4. FUNCIONES DE BÚSQUEDA WEB ACADÉMICA
# ============================================

def buscar_en_google_scholar(query, max_resultados=5):
    """
    Busca en Google Scholar usando SerpAPI o fallback.
    Nota: Necesitas una API key de SerpAPI para esto.
    """
    serpapi_key = os.environ.get('SERPAPI_KEY', None)
    
    if serpapi_key:
        try:
            url = "https://serpapi.com/search"
            params = {
                "engine": "google_scholar",
                "q": query,
                "api_key": serpapi_key,
                "num": max_resultados
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            resultados = []
            for item in data.get("organic_results", [])[:max_resultados]:
                # Extraer DOI si existe
                doi = None
                if "publication_info" in item:
                    # Intentar extraer DOI del texto
                    texto = item.get("publication_info", {}).get("summary", "")
                    doi_match = re.search(r'10\.\d{4,9}/[-.;()/:A-Z0-9]+', texto, re.IGNORECASE)
                    if doi_match:
                        doi = doi_match.group(0)
                
                resultados.append({
                    "titulo": item.get("title", "Sin título"),
                    "autores": item.get("authors", "Sin autor"),
                    "resumen": item.get("snippet", ""),
                    "año": item.get("publication_info", {}).get("year", ""),
                    "fuente": item.get("publication_info", {}).get("summary", ""),
                    "doi": doi,
                    "url": item.get("link", ""),
                    "citas": item.get("cited_by", {}).get("value", 0)
                })
            
            return resultados
        except Exception as e:
            print(f"   ⚠️ Error en SerpAPI: {e}")
            return []
    else:
        print("   ⚠️ SERPAPI_KEY no configurada. Usando búsqueda limitada.")
        return []

def buscar_con_brave(query, max_resultados=5):
    """
    Busca en web usando Brave Search API.
    Brave es excelente para encontrar artículos académicos.
    """
    if not BRAVE_API_KEY:
        return []
    
    try:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "X-Subscription-Token": BRAVE_API_KEY,
            "Accept": "application/json"
        }
        params = {
            "q": f"{query} site:ieee.org OR site:springer.com OR site:elsevier.com OR site:mdpi.com OR site:arxiv.org",
            "count": max_resultados * 2
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()
        
        resultados = []
        seen_titles = set()
        
        for item in data.get("web", {}).get("results", []):
            titulo = item.get("title", "")
            if titulo in seen_titles:
                continue
            seen_titles.add(titulo)
            
            url_art = item.get("url", "")
            
            # Intentar extraer DOI de la URL o descripción
            doi = None
            texto_completo = f"{item.get('description', '')} {item.get('extra_snippets', [''])}"
            doi_match = re.search(r'10\.\d{4,9}/[-.;()/:A-Z0-9]+', texto_completo, re.IGNORECASE)
            if doi_match:
                doi = doi_match.group(0)
            
            # Verificar si es fuente académica
            es_academico = any(dominio in url_art.lower() for dominio in 
                              ['.ieee.', '.springer.', '.elsevier.', '.mdpi.', '.arxiv.', '.sciencedirect.'])
            
            if es_academico or doi:
                resultados.append({
                    "titulo": titulo,
                    "fuente": item.get("url", ""),
                    "descripcion": item.get("description", ""),
                    "doi": doi,
                    "es_academico": es_academico
                })
                
                if len(resultados) >= max_resultados:
                    break
        
        return resultados
    
    except Exception as e:
        print(f"   ⚠️ Error en Brave Search: {e}")
        return []

def buscar_academicamente(query):
    """
    Función principal de búsqueda académica.
    Combina Google Scholar y Brave Search.
    """
    print(f"\n   🔍 Buscando información académica sobre: {query[:100]}...")
    
    resultados = []
    
    # 1. Intentar Google Scholar (más académico)
    scholar_results = buscar_en_google_scholar(query, max_resultados=3)
    if scholar_results:
        print(f"   📚 Encontrados {len(scholar_results)} resultados en Google Scholar")
        resultados.extend(scholar_results)
    
    # 2. Complementar con Brave Search
    brave_results = buscar_con_brave(query, max_resultados=2)
    if brave_results:
        print(f"   🌐 Encontrados {len(brave_results)} resultados en web académica")
        resultados.extend(brave_results)
    
    return resultados

# ============================================
# 5. FUNCIONES DE PROCESAMIENTO DE ARCHIVOS
# ============================================

def extraer_texto_pdf(ruta_pdf):
    """
    Extrae todo el texto de un archivo PDF usando PyPDF2.
    """
    try:
        print(f"   📄 Extrayendo texto del PDF: {os.path.basename(ruta_pdf)}...")
        with open(ruta_pdf, 'rb') as archivo:
            lector = PyPDF2.PdfReader(archivo)
            numero_paginas = len(lector.pages)
            print(f"   📑 Páginas detectadas: {numero_paginas}")
            
            texto_completo = ""
            for i, pagina in enumerate(lector.pages, 1):
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    texto_completo += f"\n--- PÁGINA {i} ---\n{texto_pagina}\n"
                else:
                    print(f"   ⚠️ La página {i} no contiene texto extraíble")
            
            if not texto_completo.strip():
                print("   ⚠️ El PDF no contiene texto extraíble (posiblemente escaneado)")
                return None
                
            print(f"   ✅ Texto extraído correctamente ({len(texto_completo)} caracteres)")
            return texto_completo
            
    except PyPDF2.errors.PdfReadError:
        print(f"   ❌ Error: El archivo no es un PDF válido o está corrupto")
        return None
    except Exception as e:
        print(f"   ❌ Error al leer el PDF: {e}")
        return None

def procesar_imagen_a_base64(ruta_imagen):
    """
    Convierte una imagen a formato base64 para enviarla a DeepSeek.
    """
    try:
        extension = os.path.splitext(ruta_imagen)[1].lower()
        
        mime_map = {
            '.jpg': 'jpeg',
            '.jpeg': 'jpeg',
            '.png': 'png',
            '.gif': 'gif',
            '.webp': 'webp',
            '.bmp': 'bmp'
        }
        
        if extension not in mime_map:
            print(f"   ⚠️ Formato de imagen no soportado: {extension}")
            return None
            
        with open(ruta_imagen, "rb") as archivo:
            contenido_base64 = base64.b64encode(archivo.read()).decode('utf-8')
            
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/{mime_map[extension]};base64,{contenido_base64}"
            }
        }
        
    except Exception as e:
        print(f"   ❌ Error al procesar la imagen: {e}")
        return None

def procesar_archivos(rutas):
    """
    Procesa una lista de rutas de archivos (PDFs e imágenes).
    """
    texto_pdfs = ""
    imagenes_base64 = []
    
    for ruta in rutas:
        ruta_limpia = ruta.strip().strip("'\"")
        
        if not os.path.exists(ruta_limpia):
            print(f"[ADVERTENCIA] El archivo no existe: {ruta_limpia}")
            continue
            
        extension = os.path.splitext(ruta_limpia)[1].lower()
        nombre_archivo = os.path.basename(ruta_limpia)
        
        print(f"\n[PROCESANDO] {nombre_archivo}")
        
        if extension == '.pdf':
            texto = extraer_texto_pdf(ruta_limpia)
            if texto:
                texto_pdfs += f"\n\n{'='*60}\n"
                texto_pdfs += f"📄 CONTENIDO DEL PDF: {nombre_archivo}\n"
                texto_pdfs += f"{'='*60}\n{texto}\n"
                
        elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
            img_data = procesar_imagen_a_base64(ruta_limpia)
            if img_data:
                imagenes_base64.append(img_data)
                print(f"   ✅ Imagen procesada correctamente")
                
        else:
            print(f"   ⚠️ Tipo de archivo no soportado: {extension}")
    
    return texto_pdfs, imagenes_base64

def extraer_dois_de_texto(texto):
    """
    Extrae todos los DOIs del texto generado.
    """
    doi_pattern = r'10\.\d{4,9}/[-.;()/:A-Z0-9]+'
    dois = re.findall(doi_pattern, texto, re.IGNORECASE)
    return list(set(dois))  # Eliminar duplicados

def generar_reporte_verificacion(dois, texto_completo, nombre_archivo):
    """
    Genera un archivo de verificación de citas con los DOIs extraídos.
    """
    os.makedirs(CARPETA_VERIFICACION, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_base = nombre_archivo.replace('.tex', '')
    ruta_reporte = os.path.join(CARPETA_VERIFICACION, f"{nombre_base}_verificacion_{timestamp}.txt")
    
    with open(ruta_reporte, "w", encoding="utf-8") as f:
        f.write("="*80 + "\n")
        f.write("REPORTE DE VERIFICACIÓN DE CITAS\n")
        f.write(f"Archivo: {nombre_archivo}\n")
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")
        
        f.write("DOI ENCONTRADOS EN EL TEXTO:\n")
        f.write("-"*40 + "\n")
        if dois:
            for i, doi in enumerate(dois, 1):
                f.write(f"{i}. {doi}\n")
                f.write(f"   → Verificar en: https://doi.org/{doi}\n\n")
        else:
            f.write("❌ No se encontraron DOIs en el texto.\n")
            f.write("   ADVERTENCIA: Esto puede indicar que el modelo alucinó citas.\n\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write("FRAGMENTOS DEL TEXTO CON CITAS:\n")
        f.write("-"*40 + "\n")
        
        # Buscar patrones de cita IEEE
        patron_cita = r'\\cite\{[^}]+\}'
        citas_encontradas = re.findall(patron_cita, texto_completo)
        if citas_encontradas:
            for cita in citas_encontradas[:20]:  # Mostrar primeras 20
                f.write(f"{cita}\n")
        else:
            f.write("No se encontraron comandos \\cite{} en el texto.\n")
    
    print(f"\n   📋 Reporte de verificación guardado en: {ruta_reporte}")
    return ruta_reporte

# ============================================
# 6. FUNCIÓN PRINCIPAL DEL AGENTE
# ============================================

def ejecutar_agente():
    """Función principal del agente para generar Abstract y Resumen Ejecutivo."""
    
    os.makedirs(CARPETA_BORRADORES, exist_ok=True)
    os.makedirs(CARPETA_VERIFICACION, exist_ok=True)
    
    print("\n" + "="*60)
    print("🎓 AGENTE DE GENERACIÓN DE ABSTRACT Y RESUMEN EJECUTIVO")
    print("   CON BÚSQUEDA ACADÉMICA Y VERIFICACIÓN DE CITAS")
    print("="*60)
    print("\n📌 INFORMACIÓN:")
    print("   - Modelo: deepseek-v4-pro")
    print("   - Contexto: Capítulos completos de la tesis")
    print("   - Salida: Abstract y Resumen Ejecutivo en .tex")
    print("   - Idiomas: Español e Inglés")
    print("="*60 + "\n")

    while True:
        try:
            print("\n" + "─"*60)
            instruccion = input("📝 ¿Qué deseas generar?\n   (Ej: 'Genera el Abstract y Resumen Ejecutivo')\n> ").strip()
            
            if not instruccion:
                print("[ADVERTENCIA] Debes ingresar una instrucción válida.")
                continue
                
            if instruccion.lower() in ['salir', 'exit', 'quit', 'q']:
                print("\n[INFO] Cerrando el agente. ¡Mucho éxito con tu tesis! 🎉")
                break

            print("\n" + "─"*60)
            archivos_input = input("📎 (Opcional) Arrastra archivos (PDFs o Imágenes) separados por comas\n   (Presiona Enter si no hay archivos):\n> ")
            rutas_archivos = [a.strip() for a in archivos_input.split(',') if a.strip()] if archivos_input.strip() else []

            print("\n" + "─"*60)
            nombre_archivo = input("💾 Nombre del archivo .tex de salida\n   (Ej. 00_Resumen_Abstract.tex):\n> ").strip()
            
            if not nombre_archivo:
                nombre_archivo = "00_Resumen_Abstract.tex"
            elif not nombre_archivo.endswith('.tex'):
                nombre_archivo += '.tex'
            
            ruta_salida = os.path.join(CARPETA_BORRADORES, nombre_archivo)
            
            # ============================================
            # PROCESAR ARCHIVOS
            # ============================================
            print("\n" + "─"*60)
            print("[PROCESANDO ARCHIVOS]")
            texto_pdfs, imagenes_base64 = procesar_archivos(rutas_archivos)

            # ============================================
            # CONSTRUIR EL PROMPT
            # ============================================
            print("\n" + "─"*60)
            print("[CONSTRUYENDO PROMPT]")
            
            mensajes = [
                {"role": "system", "content": INSTRUCCIONES_AGENTE}
            ]
            
            contenido_usuario = []
            
            # Texto base con todo el contexto de los capítulos
            texto_base = f"""
            CONTEXTO COMPLETO DE LA TESIS (TODOS LOS CAPÍTULOS):
            {CONTEXTO_CAPITULOS}

            ORDEN DE GENERACIÓN:
            {instruccion}
            """
            
            # Agregar texto de PDFs si existen
            if texto_pdfs:
                texto_base += f"\n\n--- INFORMACIÓN EXTRAÍDA DE PDFs ---\n{texto_pdfs}"
            
            contenido_usuario.append({"type": "text", "text": texto_base})
            
            if imagenes_base64:
                print(f"   🖼️ Agregando {len(imagenes_base64)} imagen(es)")
                contenido_usuario.extend(imagenes_base64)
            
            mensajes.append({"role": "user", "content": contenido_usuario})
            
            # ============================================
            # LLAMAR A LA API DE DEEPSEEK
            # ============================================
            print("\n" + "─"*60)
            print("🚀 ENVIANDO A DEEPSEEK V4 PRO...")
            print("   (Esto puede tomar varios segundos)")
            
            try:
                response = cliente.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=mensajes,
                    temperature=0.1,
                    top_p=0.3,
                    max_tokens=16384,
                    stream=False
                )
                
                texto_generado = response.choices[0].message.content
                
                # Mostrar estadísticas
                if hasattr(response, 'usage'):
                    print(f"\n   📊 Tokens usados:")
                    print(f"      - Entrada: {response.usage.prompt_tokens:,}")
                    print(f"      - Salida:  {response.usage.completion_tokens:,}")
                    print(f"      - Total:   {response.usage.total_tokens:,}")
                    costo = (response.usage.prompt_tokens * 0.435 + response.usage.completion_tokens * 0.87) / 1_000_000
                    print(f"   💰 Costo aproximado: ${costo:.4f}")
                
                # ============================================
                # GUARDAR ARCHIVO
                # ============================================
                with open(ruta_salida, "w", encoding="utf-8") as f:
                    f.write(texto_generado)
                
                print(f"\n✅ [ÉXITO] Generación completada.")
                print(f"   📁 Archivo guardado en: '{ruta_salida}'")
                print(f"   📏 Tamaño: {len(texto_generado):,} caracteres")
                
            except Exception as api_error:
                error_msg = str(api_error)
                if "insufficient_balance" in error_msg.lower() or "402" in error_msg:
                    print("\n❌ [ERROR DE FACTURACIÓN]")
                    print("   Tu cuenta de DeepSeek no tiene saldo suficiente.")
                    print("   📌 Solución: Recarga fondos en https://platform.deepseek.com/")
                elif "invalid_api_key" in error_msg.lower() or "401" in error_msg:
                    print("\n❌ [ERROR DE AUTENTICACIÓN]")
                    print("   Tu API Key de DeepSeek es inválida o expiró.")
                else:
                    raise api_error

        except KeyboardInterrupt:
            print("\n\n[INFO] Proceso interrumpido por el usuario.")
            break
            
        except Exception as e:
            print(f"\n❌ [ERROR INESPERADO]")
            print(f"   Detalles: {e}")
            print("\n   📌 Sugerencias:")
            print("   1. Verifica tu conexión a internet")
            print("   2. Revisa que la API Key sea correcta")
            print("   3. Confirma que tienes saldo disponible")
            print("   4. Si el error persiste, reinicia el programa")

if __name__ == "__main__":
    ejecutar_agente()