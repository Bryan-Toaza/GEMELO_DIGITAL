from controller import Robot

# 1. Inicializar el robot
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# 2. Vincular el motor
motor_soporte = robot.getDevice("Soporte_Funda_mov2")

# 3. Configuración de Tiempos
tiempo_delay_inicial = 6 # Segundos que la máquina espera antes de arrancar
tiempo_ciclo_total = 6   # Cuánto dura un ciclo completo (abrir + cerrar)
tiempo_abierto = 3      # Cuántos segundos permanece abajo la trampa

print(f"Máquina en Standby. Esperando {tiempo_delay_inicial} segundos...")

# Bucle principal de la simulación
while robot.step(timestep) != -1:
    
    # Obtener el tiempo actual de la simulación
    tiempo_actual = robot.getTime()
    
    # --- MÁQUINA DE ESTADOS FINITOS ---
    
    # ESTADO 1: DELAY / STANDBY
    if tiempo_actual < tiempo_delay_inicial:
        # Mantenemos el soporte en su posición inicial cerrada
        motor_soporte.setPosition(0.0)
        
    # ESTADO 2: PRODUCCIÓN EN BUCLE
    else:
        # Restamos el delay al tiempo actual para que nuestro ciclo 
        # matemático empiece limpiamente desde cero.
        tiempo_efectivo = tiempo_actual - tiempo_delay_inicial
        
        tiempo_en_ciclo = tiempo_efectivo % tiempo_ciclo_total
        
        if tiempo_en_ciclo < tiempo_abierto:
            motor_soporte.setPosition(-1.4)  # 90 grados (Abierto/Dejando caer)
        else:
            motor_soporte.setPosition(0.0)   # 0 grados (Cerrado/Posición inicial)