#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
Programa para fusionar tramas NMEA de un módem GPS en Raspberry Pi
Procesa: $GPVTG, $GPGGA, $GPGSA, $GPGSV, $GPGLL y $GPRMC
Incluye interfaz gráfica para visualización de datos
"""

import serial
import time
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime

class GPSFusion:
    def __init__(self, puerto='/dev/serial0', baudrate=9600, timeout=1, debug=False):
        """Inicializa la conexión serial con el módem GPS"""
        self.puerto = puerto
        self.baudrate = baudrate
        self.timeout = timeout
        self.conexion = None
        self.datos_gps = {
            'timestamp': '',
            'latitud': '',
            'longitud': '',
            'altitud': '',
            'velocidad': '',
            'curso': '',
            'fecha': '',
            'hora': '',
            'satelites_visibles': 0,
            'satelites_usados': 0,
            'calidad_fix': '',
            'hdop': '',
            'pdop': '',
            'vdop': '',
            'satelites_info': []
        }
        self.tramas_procesadas = 0
        self.archivo_log = f"gps_fusion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.debug = True  # Activar modo debug
        self.ejecutando = False
        self.GPSFusion = None  # <- Previene AttributeError
        self.gps = None
        self.callback_actualizacion = None
        
    def definir_callback(self, callback):
        """Define una función de callback para actualizar la UI"""
        self.callback_actualizacion = callback
        
    def debug_print(self, mensaje):
        """Imprime mensajes de debug si el modo debug está activado"""
        if self.debug:
            print(f"DEBUG: {mensaje}")
        
    def conectar(self):
        """Establece la conexión con el puerto serial"""
        try:
            self.conexion = serial.Serial(
                port=self.puerto,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            print(f"Conexión establecida en {self.puerto} a {self.baudrate} baudios")
            return True
        except Exception as e:
            print(f"Error al conectar con el GPS: {e}")
            return False
    
    def desconectar(self):
        """Cierra la conexión serial"""
        if self.conexion and self.conexion.is_open:
            self.conexion.close()
            print("Conexión cerrada")

    def detener(self):
        if self.GPSFusion is not None:
            self.GPSFusion.detener()
            print("GPSFusion detenido correctamente.")
        else:
            print("GPSFusion no estaba en ejecución.")
    
    def calcular_checksum(self, sentencia):
        """Calcula el checksum de una sentencia NMEA"""
        checksum = 0
        for char in sentencia[1:]:  # Omitir el $ inicial
            if char == '*':
                break
            checksum ^= ord(char)
        return f"{checksum:02X}"  # Devuelve el checksum en hexadecimal
    
    def validar_checksum(self, sentencia):
        """Valida el checksum de una sentencia NMEA"""
        if '*' not in sentencia:
            return False
        
        partes = sentencia.split('*')
        if len(partes) != 2:
            return False
        
        checksum_calculado = self.calcular_checksum(sentencia)
        checksum_recibido = partes[1].strip().upper()
        
        return checksum_calculado == checksum_recibido
    
    def convertir_a_decimal(self, coordenada_str):
        """
        Convierte una coordenada NMEA en formato ddmm.mmmm a grados decimales.
        Por ejemplo: 0215.87414 -> 2 + (15.87414 / 60) = 2.26457
        """
        if not coordenada_str or coordenada_str == '':
            return None

        try:
            # Separar grados y minutos
            grados = int(coordenada_str[:2])
            minutos = float(coordenada_str[2:])
            return round(grados + minutos / 60, 6)
        except ValueError as e:
            if self.debug:
                print(f"Error en conversión de coordenada: {e}")
            return None
   
    def convertir_coordenada(self, valor_str, direccion):
        """Convierte una coordenada NMEA a formato decimal"""
        try:
            if not valor_str or not valor_str.strip():
                return ""
            
            valor = float(valor_str)
            grados = int(valor / 100)
            minutos = valor - (grados * 100)
            decimal = grados + (minutos / 60)
            
            # Ajustar según la dirección (S/W son negativas)
            if direccion in ['S', 'W']:
                decimal = -decimal
                
            return f"{decimal:.6f}"
        except ValueError:
            self.debug_print(f"Error al convertir coordenada: '{valor_str}' con dirección '{direccion}'")
            return ""
    
    def convertir_coordenada(valor, direccion):
        """
        Convierte una coordenada NMEA (lat o lon) a decimal.
        Ejemplo: 0215.87537, 'S' -> -2.2645895
        """
        try:
            coord = float(valor)
            grados = int(coord / 100)
            minutos = coord - (grados * 100)
            decimal = grados + (minutos / 60)
            if direccion in ['S', 'W']:
                decimal *= -1
            return decimal
        except ValueError:
            return None

    # PROCESAMIENTO DE TRAMAS *******************************************************************************************
    
    def procesar_gpvtg(self, datos):
        """Procesa la trama $GPVTG (Track Made Good and Ground Speed)"""
        try:
            campos = datos.split(',')
        
            if len(campos) >= 8:
                # Procesar curso (solo si es numérico)
                if campos[1].replace('.', '', 1).isdigit():  # Verificar si es numérico
                    self.datos_gps['curso'] = float(campos[1])
            
                # Procesar velocidad (solo si es numérico)
                if campos[7].replace('.', '', 1).isdigit():  # Verificar si es numérico
                    self.datos_gps['velocidad'] = float(campos[7])
        
            return True
        except Exception as e:
            print(f"Error al procesar GPVTG: {e}")
            return False

    def procesar_gpgga(self, datos):
        """Procesa la trama GPGGA"""
        try:
            self.datos_gps["timestamp"] = datos[1]

            lat_raw = datos[2]
            lat_dir = datos[3]
            lon_raw = datos[4]
            lon_dir = datos[5]

            latitud = self.convertir_a_decimal(lat_raw)
            if latitud is not None and lat_dir == 'S':
                latitud *= -1

            longitud = self.convertir_a_decimal(lon_raw)
            if longitud is not None and lon_dir == 'W':
                longitud *= -1

            self.datos_gps["latitud"] = latitud
            self.datos_gps["longitud"] = longitud

            self.datos_gps["calidad_fix"] = datos[6]
            self.datos_gps["satélites_utilizados"] = int(datos[7])
            self.datos_gps["altitud"] = float(datos[9]) if datos[9] else None

            if self.debug:
                print(f"DEBUG: Contenido GPGGA: {','.join(datos)}")
        except Exception as e:
            print(f"Error al procesar GPGGA: {e}")
    
    def procesar_gpgsa(self, datos):
        """Procesa la trama $GPGSA (GPS DOP and Active Satellites)"""
        try:
            campos = datos.split(',')
            if len(campos) >= 18:
                if campos[15]:
                    self.datos_gps['pdop'] = float(campos[15])
                if campos[16]:
                    self.datos_gps['hdop'] = float(campos[16])
                if campos[17]:
                    vdop = campos[17].split('*')[0] if '*' in campos[17] else campos[17]
                    self.datos_gps['vdop'] = float(vdop)
            return True
        except Exception as e:
            print(f"Error al procesar GPGSA: {e}")
            self.debug_print(f"Contenido GPGSA: {datos}")
            return False
    
    def procesar_gpgsv(self, datos):
        """Procesa la trama $GPGSV (GPS Satellites in View)"""
        try:
            campos = datos.split(',')
            if len(campos) >= 4:
                num_msg = int(campos[1]) if campos[1].isdigit() else 0
                msg_num = int(campos[2]) if campos[2].isdigit() else 0
                sat_visibles = int(campos[3]) if campos[3].isdigit() else 0

                if msg_num == 1:
                    self.datos_gps['satelites_visibles'] = sat_visibles
                    self.datos_gps['satelites_info'] = []

                for i in range(4):  # hasta 4 satélites por trama
                    idx = 4 + i * 4
                    if len(campos) > idx and campos[idx]:
                        sat_id = campos[idx]
                        elevacion = int(campos[idx + 1]) if len(campos) > idx + 1 and campos[idx + 1].isdigit() else 0
                        azimut = int(campos[idx + 2]) if len(campos) > idx + 2 and campos[idx + 2].isdigit() else 0

                        snr_str = campos[idx + 3] if len(campos) > idx + 3 else '0'
                        snr = int(snr_str.split('*')[0]) if snr_str and snr_str.split('*')[0].isdigit() else 0

                        self.datos_gps['satelites_info'].append({
                            'id': sat_id,
                            'elevacion': elevacion,
                            'azimut': azimut,
                            'snr': snr
                        })
            return True
        except Exception as e:
            print(f"Error al procesar GPGSV: {e}")
            self.debug_print(f"Contenido GPGSV: {datos}")
            return False
    
    def procesar_gpgll(self, datos):
        """Procesa la trama GPGLL"""
        try:
            lat_raw = datos[1]
            lat_dir = datos[2]
            lon_raw = datos[3]
            lon_dir = datos[4]
            timestamp = datos[5]

            latitud = self.convertir_a_decimal(lat_raw)
            if latitud is not None and lat_dir == 'S':
                latitud *= -1

            longitud = self.convertir_a_decimal(lon_raw)
            if longitud is not None and lon_dir == 'W':
                longitud *= -1

            self.datos_gps["timestamp"] = timestamp
            self.datos_gps["latitud"] = latitud
            self.datos_gps["longitud"] = longitud

            if self.debug:
                print(f"DEBUG: Contenido GPGLL: {','.join(datos)}")
        except Exception as e:
            print(f"Error al procesar GPGLL: {e}")
    
    def procesar_gprmc(self, datos):
        """Procesa la trama GPRMC"""
        try:
            self.datos_gps["timestamp"] = datos[1]

            velocidad_nudos = datos[7]
            if velocidad_nudos:
                velocidad_kmh = float(velocidad_nudos) * 1.852
                self.datos_gps["velocidad"] = round(velocidad_kmh, 2)

            curso = datos[8]
            if curso:
                self.datos_gps["curso"] = float(curso)

            if self.debug:
                print(f"DEBUG: Contenido GPRMC: {','.join(datos)}")
        except Exception as e:
            print(f"Error al procesar GPRMC: {e}")

    def procesar_trama(self, trama):
        """Procesa una trama NMEA y actualiza los datos GPS"""
        trama = trama.strip()
        if not trama:
            return False
        
        # Verificar formato válido de trama NMEA
        if not trama.startswith('$'):
            return False
        
        # Validar checksum si está presente
        if '*' in trama and not self.validar_checksum(trama):
            self.debug_print(f"Checksum inválido en trama: {trama}")
            return False
        
        # Mostrar trama en modo debug
        self.debug_print(f"Trama recibida: {trama}")
        
        # Obtener el tipo de trama y los datos
        try:
            partes = trama.split(',', 1)
            tipo_trama = partes[0]
            datos = partes[1] if len(partes) > 1 else ""
            
            resultado = False
            
            # Procesamiento según el tipo de trama
            if tipo_trama == '$GPVTG':
                resultado = self.procesar_gpvtg(datos)
            elif tipo_trama == '$GPGGA':
                resultado = self.procesar_gpgga(datos)
            elif tipo_trama == '$GPGSA':
                resultado = self.procesar_gpgsa(datos)
            elif tipo_trama == '$GPGSV':
                resultado = self.procesar_gpgsv(datos)
            elif tipo_trama == '$GPGLL':
                resultado = self.procesar_gpgll(datos)
            elif tipo_trama == '$GPRMC':
                resultado = self.procesar_gprmc(datos)
            
            if resultado:
                self.tramas_procesadas += 1
                if self.callback_actualizacion:
                    self.callback_actualizacion(self.datos_gps.copy())
                
            return resultado
            
        except Exception as e:
            print(f"Error al procesar trama {trama}: {e}")
            return False
    
    # FIN DE PROCESAMIENTO DE TRAMAS ********************************************************************************

    def guardar_log(self, mostrar=True):
        """Guarda los datos GPS en un archivo JSON y los muestra por pantalla"""
        try:
            with open(self.archivo_log, 'a') as f:
                datos_json = json.dumps(self.datos_gps, indent=2)
                f.write(datos_json + '\n')
                
            if mostrar:
                print("\n----- Datos GPS Fusionados -----")
                print(f"Timestamp: {self.datos_gps['timestamp']}")
                print(f"Posición: {self.datos_gps['latitud']}, {self.datos_gps['longitud']}")
                print(f"Altitud: {self.datos_gps['altitud']} m")
                print(f"Velocidad: {self.datos_gps['velocidad']} km/h")
                print(f"Curso: {self.datos_gps['curso']}°")
                print(f"Satélites visibles: {self.datos_gps['satelites_visibles']}")
                print(f"Satélites utilizados: {self.datos_gps['satelites_usados']}")
                print(f"Calidad fix: {self.datos_gps['calidad_fix']}")
                print(f"HDOP: {self.datos_gps['hdop']}")
                print(f"PDOP: {self.datos_gps['pdop']}")
                print(f"VDOP: {self.datos_gps['vdop']}")
                print(f"Tramas procesadas: {self.tramas_procesadas}")
                print("--------------------------------\n")
                
            return True
        except Exception as e:
            print(f"Error al guardar log: {e}")
            return False
    
    def iniciar_lectura(self, duracion=None, intervalo_log=10):
        """Inicia la lectura continua de tramas GPS en un hilo separado"""
        if not self.conectar():
            return False
        
        self.ejecutando = True
        thread = threading.Thread(target=self._loop_lectura, args=(duracion, intervalo_log))
        thread.daemon = True  # El hilo se detendrá cuando el programa principal termine
        thread.start()
        
        return True
    
    def _loop_lectura(self, duracion=None, intervalo_log=10):
        """Bucle de lectura que se ejecuta en un hilo separado"""
        print("Iniciando lectura de datos GPS...")
        
        try:
            inicio = time.time()
            ultimo_log = inicio
            
            while self.ejecutando:
                # Verificar si debemos finalizar por duración
                if duracion and (time.time() - inicio) > duracion:
                    print(f"Finalizado por tiempo: {duracion} segundos")
                    break
                
                # Leer una línea del puerto serial
                if self.conexion.in_waiting:
                    linea = self.conexion.readline().decode('utf-8', errors='replace').strip()
                    if linea:
                        # Procesar la trama NMEA
                        self.procesar_trama(linea)

                        # Enviar datos actualizados a la interfaz gráfica si hay callback
                        if self.callback_actualizacion:
                            self.callback_actualizacion(self.datos_gps.copy())  # Usamos .copy() para evitar que la interfaz gráfica manipule directamente el diccionario original mientras aún se está llenando.
                
                # Guardar y mostrar el log periódicamente
                if (time.time() - ultimo_log) > intervalo_log:
                    self.guardar_log()
                    ultimo_log = time.time()
                
                time.sleep(0.01)  # Pequeña pausa para no saturar la CPU
                
        except Exception as e:
            print(f"Error durante la lectura: {e}")
        finally:
            self.desconectar()
            self.guardar_log()  # Guardar datos antes de salir

class GPS:
    def __init__(self):
        """Simula la conexión a un GPS y la lectura de datos NMEA"""
        self.ejecutando = False
        self.callback_actualizacion = None
        
    def iniciar_lectura(self, duracion=60):
        """Simula la lectura de datos GPS durante 'duracion' segundos"""
        self.ejecutando = True
        start_time = time.time()
        
        while self.ejecutando and time.time() - start_time < duracion:
            # Simular datos GPS
            datos = {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'latitud': "40.7128 N",
                'longitud': "74.0060 W",
                'altitud': "10.5 m",
                'velocidad': "50 km/h",
                'curso': "180°",
                'satelites_visibles': "8",
                'hdop': "0.8",
                'pdop': "1.2",
                'vdop': "1.1",
                'calidad_fix': "3D"
            }
            
            # Si hay un callback, se actualizan los datos
            if self.callback_actualizacion:
                self.callback_actualizacion(datos)
            
            # Simular un intervalo de tiempo entre lecturas
            time.sleep(1)

    def detener_lectura(self):
        """Detiene la lectura de datos GPS"""
        self.ejecutando = False

class AplicacionGPS:
    def __init__(self, root):
        """Inicializa la interfaz gráfica para la aplicación GPS"""
        self.root = root
        self.root.title("Fusión NMEA GPS")
        self.root.geometry("800x600")
        self.root.configure(bg="#f0f0f0")
        
        # Variable para almacenar el objeto GPS
        self.gps = None
        
        # Variables para los controles de configuración
        self.var_puerto = tk.StringVar(value='/dev/serial0')
        self.var_baudrate = tk.IntVar(value=9600)
        self.var_debug = tk.BooleanVar(value=False)
        
        # Crear los componentes de la interfaz
        self.crear_interfaz()
        
    def crear_interfaz(self):
        """Crea todos los elementos de la interfaz gráfica"""
        # Frame para la configuración
        frm_config = ttk.LabelFrame(self.root, text="Configuración")
        frm_config.pack(fill="x", padx=10, pady=5)
        
        # Control de puerto
        ttk.Label(frm_config, text="Puerto:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(frm_config, textvariable=self.var_puerto, width=20).grid(row=0, column=1, padx=5, pady=5)
        
        # Control de baudrate
        ttk.Label(frm_config, text="Baudrate:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        baudrates = [4800, 9600, 19200, 38400, 57600, 115200]
        cmb_baudrate = ttk.Combobox(frm_config, textvariable=self.var_baudrate, values=baudrates, width=10)
        cmb_baudrate.grid(row=0, column=3, padx=5, pady=5)
        
        # Control de depuración
        ttk.Checkbutton(frm_config, text="Modo Debug", variable=self.var_debug).grid(row=0, column=4, padx=5, pady=5)
        
        # Botones de control
        frm_botones = ttk.Frame(frm_config)
        frm_botones.grid(row=0, column=5, padx=5, pady=5)
        
        self.btn_iniciar = ttk.Button(frm_botones, text="Iniciar", command=self.iniciar)
        self.btn_iniciar.pack(side="left", padx=2)
        
        self.btn_detener = ttk.Button(frm_botones, text="Detener", command=self.detener, state="disabled")
        self.btn_detener.pack(side="left", padx=2)
        
        # Frame para los datos GPS
        frm_datos = ttk.LabelFrame(self.root, text="Datos GPS")
        frm_datos.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Crear grid para los datos principales
        frm_grid = ttk.Frame(frm_datos)
        frm_grid.pack(fill="x", padx=5, pady=5)
        
        # Primera fila: Timestamp y Fix
        ttk.Label(frm_grid, text="Timestamp:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.lbl_timestamp = ttk.Label(frm_grid, text="--", width=20)
        self.lbl_timestamp.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frm_grid, text="Calidad Fix:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.lbl_fix = ttk.Label(frm_grid, text="--", width=5)
        self.lbl_fix.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        # Segunda fila: Coordenadas
        ttk.Label(frm_grid, text="Latitud:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.lbl_latitud = ttk.Label(frm_grid, text="--", width=15)
        self.lbl_latitud.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frm_grid, text="Longitud:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.lbl_longitud = ttk.Label(frm_grid, text="--", width=15)
        self.lbl_longitud.grid(row=1, column=3, padx=5, pady=5, sticky="w")
        
        # Tercera fila: Altitud y velocidad
        ttk.Label(frm_grid, text="Altitud:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.lbl_altitud = ttk.Label(frm_grid, text="--", width=10)
        self.lbl_altitud.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frm_grid, text="Velocidad:").grid(row=2, column=2, padx=5, pady=5, sticky="w")
        self.lbl_velocidad = ttk.Label(frm_grid, text="--", width=10)
        self.lbl_velocidad.grid(row=2, column=3, padx=5, pady=5, sticky="w")
        
        # Cuarta fila: Curso y satélites
        ttk.Label(frm_grid, text="Curso:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.lbl_curso = ttk.Label(frm_grid, text="--", width=10)
        self.lbl_curso.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frm_grid, text="Satélites:").grid(row=3, column=2, padx=5, pady=5, sticky="w")
        self.lbl_satelites = ttk.Label(frm_grid, text="--", width=15)
        self.lbl_satelites.grid(row=3, column=3, padx=5, pady=5, sticky="w")
        
        # Quinta fila: HDOP, PDOP, VDOP
        ttk.Label(frm_grid, text="HDOP:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.lbl_hdop = ttk.Label(frm_grid, text="--", width=5)
        self.lbl_hdop.grid(row=4, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frm_grid, text="PDOP:").grid(row=4, column=2, padx=5, pady=5, sticky="w")
        self.lbl_pdop = ttk.Label(frm_grid, text="--", width=5)
        self.lbl_pdop.grid(row=4, column=3, padx=5, pady=5, sticky="w")
        
        ttk.Label(frm_grid, text="VDOP:").grid(row=4, column=4, padx=5, pady=5, sticky="w")
        self.lbl_vdop = ttk.Label(frm_grid, text="--", width=5)
        self.lbl_vdop.grid(row=4, column=5, padx=5, pady=5, sticky="w")


    def iniciar(self):
        """Inicia la lectura de datos GPS"""
        # Aquí se crearía la conexión con el GPS
        self.gps = GPSFusion(puerto=self.var_puerto.get(),
                             baudrate=self.var_baudrate.get(),
                             # timeout=self.var_timeout.get(),
                             debug=self.var_debug.get()
                             )  # Debes tener una clase GPS que maneje la lectura
        self.gps.callback_actualizacion = self.actualizar_datos
        self.gps.iniciar_lectura(duracion=60)  # Tiempo en segundos
        self.btn_iniciar.config(state="disabled")
        self.btn_detener.config(state="normal")
    
    def detener(self):
        """Detiene la lectura de datos GPS"""
        if self.gps:
            self.gps.ejecutando = False
        self.btn_iniciar.config(state="normal")
        self.btn_detener.config(state="disabled")
    
    def actualizar_datos(self, datos):
        """Actualiza los datos en la interfaz gráfica"""
        # Actualiza los labels con los datos GPS
        self.lbl_timestamp.config(text=datos['timestamp'])
        self.lbl_latitud.config(text=datos['latitud'])
        self.lbl_longitud.config(text=datos['longitud'])
        self.lbl_altitud.config(text=datos['altitud'])
        self.lbl_velocidad.config(text=datos['velocidad'])
        self.lbl_curso.config(text=datos['curso'])
        self.lbl_satelites.config(text=datos['satelites_visibles'])
        self.lbl_hdop.config(text=datos['hdop'])
        self.lbl_pdop.config(text=datos['pdop'])
        self.lbl_vdop.config(text=datos['vdop'])
        self.lbl_fix.config(text=datos['calidad_fix'])

# Creación de la ventana principal
root = tk.Tk()
app = AplicacionGPS(root)
root.mainloop()
