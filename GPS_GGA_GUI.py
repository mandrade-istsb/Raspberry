import serial
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timedelta
import time
import os
import csv
import json

# Crear la ventana principal
root = tk.Tk()
root.title("DINDES - SISTDAexpress")
root.geometry("600x750")  # Aumentado para los nuevos controles

# Variable de control para evitar el error al salir
running = True

# Tiempo máximo (en segundos) sin datos del GPS para considerarlo desconectado
GPS_TIMEOUT = 5
last_gps_data_time = None

# Configuración del puerto serie
try:
    ser = serial.Serial('/dev/serial0', baudrate=9600, timeout=1)
    print("Puerto serie abierto correctamente")
except Exception as e:
    print(f"Error al abrir el puerto serie: {e}")
    ser = None

# Configuración de la zona horaria (UTC -5 para Ecuador)
UTC_OFFSET = -5  

# Directorio para guardar los archivos
DATA_DIR = os.path.join(os.path.expanduser("~"), "gps_data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def check_gps_status():
    """Verifica el estado del GPS basado en el tiempo desde el último dato recibido"""
    if last_gps_data_time is None:
        gps_status_var.set("Sin datos")
        gps_status_label.config(foreground="red")
        return False
    
    time_diff = (datetime.now() - last_gps_data_time).total_seconds()
    if time_diff > GPS_TIMEOUT:
        gps_status_var.set("GPS Desconectado")
        gps_status_label.config(foreground="red")
        return False
    else:
        gps_status_var.set("GPS Conectado")
        gps_status_label.config(foreground="green")
        return True

def read_gps_data():
    """Lee datos del puerto serie y actualiza la interfaz"""
    if not running:
        return  

    # Actualizar la hora del sistema cada segundo
    system_time = datetime.now().strftime("%H:%M:%S")
    data_vars["Hora Sistema"].set(system_time)
    
    # Verificar estado del GPS
    check_gps_status()

    # Leer datos GPS si el puerto está disponible
    if ser and ser.is_open:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("$GPGGA"):
                    global last_gps_data_time
                    last_gps_data_time = datetime.now()
                    parse_gpgga(line)
                    
        except Exception as e:
            print(f"Error al leer el puerto serie: {e}")

    # Programar la próxima lectura si el programa sigue en ejecución
    if running:
        root.after(1000, read_gps_data)

def safe_exit():
    """Detiene la lectura de GPS y cierra la interfaz"""
    global running
    running = False  # Detiene la ejecución de after()
    if ser and ser.is_open:
        ser.close()  # Cerrar el puerto serie
    root.destroy()

def convert_utc_to_local(utc_time_str, utc_offset):
    """Convierte la hora UTC del GPS a hora local"""
    if not utc_time_str:
        return "--:--:--"
    try:
        # El formato puede tener decimales o no
        if "." in utc_time_str:
            utc_time = datetime.strptime(utc_time_str, "%H%M%S.%f")
        else:
            utc_time = datetime.strptime(utc_time_str, "%H%M%S")
        local_time = utc_time + timedelta(hours=utc_offset)
        return local_time.strftime("%H:%M:%S")
    except ValueError as e:
        print(f"Error al convertir hora GPS: {e}, valor: {utc_time_str}")
        return "--:--:--"

def convert_to_dms(degrees_minutes, direction):
    """Convierte coordenadas al formato grados, minutos, dirección"""
    if not degrees_minutes or not direction:
        return "---"
    try:
        d, m = divmod(float(degrees_minutes), 100)
        return f"{int(d)}°{m:.3f}'{direction}"
    except ValueError:
        return "---"

def convert_to_decimal(degrees_minutes, direction):
    """Convierte coordenadas al formato decimal puro sin dirección"""
    if not degrees_minutes or not direction:
        return "---"
    try:
        d, m = divmod(float(degrees_minutes), 100)
        decimal = d + (m / 60)
        if direction in ["S", "W"]:
            decimal *= -1
        return f"{decimal:.6f}"
    except ValueError:
        return "---"

def parse_gpgga(sentence):
    """Decodifica la trama $GPGGA y actualiza la interfaz gráfica"""
    fields = sentence.split(',')

    if len(fields) < 15:
        return

    try:
        time_utc = fields[1]  
        lat = fields[2]
        lat_dir = fields[3]
        lon = fields[4]
        lon_dir = fields[5]
        quality = fields[6]
        satellites = fields[7]
        hdop = fields[8]
        altitude = fields[9]
        geoidal = fields[11]

        # Interpretación de la calidad de señal
        quality_text = {
            "0": "Sin fix",
            "1": "GPS fix",
            "2": "DGPS fix"
        }.get(quality, quality)

        # Conversión de datos
        local_time = convert_utc_to_local(time_utc, UTC_OFFSET)
        lat_dms = convert_to_dms(lat, lat_dir)
        lon_dms = convert_to_dms(lon, lon_dir)
        lat_decimal = convert_to_decimal(lat, lat_dir)
        lon_decimal = convert_to_decimal(lon, lon_dir)

        # Actualizar variables de la interfaz
        data_vars["Hora GPS"].set(local_time)
        data_vars["Latitud"].set(lat_dms)
        data_vars["Longitud"].set(lon_dms)
        data_vars["Calidad de Señal"].set(quality_text)
        data_vars["Satélites en Uso"].set(satellites)
        data_vars["Precisión HDOP"].set(hdop)
        data_vars["Altitud"].set(f"{altitude} m")
        data_vars["Separación Geoidal"].set(f"{geoidal} m")

        # Actualizar últimas coordenadas (en decimal puro)
        last_latitude.set(lat_decimal)
        last_longitude.set(lon_decimal)
        update_formatted_message()
        
        # Actualizar tiempo del último dato recibido
        time_since_var.set("0s")
        
    except Exception as e:
        print(f"Error al decodificar GPGGA: {e}")

def update_time_since_last_data():
    """Actualiza el tiempo transcurrido desde el último dato GPS recibido"""
    if not running:
        return
        
    if last_gps_data_time:
        time_diff = (datetime.now() - last_gps_data_time).total_seconds()
        time_since_var.set(f"{int(time_diff)}s")
    else:
        time_since_var.set("---")
        
    # Programar la próxima actualización
    root.after(1000, update_time_since_last_data)

def save_point():
    """Guarda el punto actual con coordenadas y mensaje en un archivo CSV"""
    # Verificar si hay datos válidos de GPS
    lat = last_latitude.get()
    lon = last_longitude.get()
    
    if lat == "---" or lon == "---":
        messagebox.showerror("Error", "No hay coordenadas GPS válidas para guardar")
        return
    
    # Obtener el mensaje actual
    message = saved_message.get()
    if message == "---":
        message = message_text.get("1.0", "end").strip()[:50]
        if not message:
            message = "Punto GPS"
    
    # Preparar los datos
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    point_data = {
        "timestamp": timestamp,
        "latitude": lat,
        "longitude": lon,
        "altitude": data_vars["Altitud"].get(),
        "satellites": data_vars["Satélites en Uso"].get(),
        "quality": data_vars["Calidad de Señal"].get(),
        "hdop": data_vars["Precisión HDOP"].get(),
        "message": message
    }
    
    # Guardar en CSV
    csv_file = os.path.join(DATA_DIR, "gps_points.csv")
    file_exists = os.path.isfile(csv_file)
    
    with open(csv_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=point_data.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(point_data)
    
    # También guardar como punto individual en JSON para fácil acceso
    point_filename = f"point_{timestamp.replace(' ', '_').replace(':', '-')}.json"
    json_file = os.path.join(DATA_DIR, point_filename)
    
    with open(json_file, 'w') as f:
        json.dump(point_data, f, indent=4)
    
    status_label.config(text=f"Punto guardado en: {DATA_DIR}")
    root.after(3000, lambda: status_label.config(text=""))
    
    # Actualizar la lista de puntos guardados
    update_saved_points()

def export_all_points():
    """Exporta todos los puntos a un archivo seleccionado por el usuario"""
    # Obtener la ubicación del archivo de salida
    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        title="Guardar archivo de puntos GPS"
    )
    
    if not file_path:
        return  # Usuario canceló
    
    # Verificar si existe el archivo de puntos
    csv_file = os.path.join(DATA_DIR, "gps_points.csv")
    if not os.path.isfile(csv_file):
        messagebox.showinfo("Información", "No hay puntos guardados para exportar")
        return
    
    # Copiar el archivo
    try:
        with open(csv_file, 'r') as source:
            with open(file_path, 'w') as dest:
                dest.write(source.read())
        messagebox.showinfo("Éxito", f"Datos exportados a:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Error al exportar datos: {e}")

def start_tracking():
    """Inicia el seguimiento continuo de puntos GPS"""
    global tracking
    if tracking.get():
        # Iniciar seguimiento
        track_status_var.set("ACTIVO")
        track_status_label.config(foreground="green")
        save_point()  # Guardar punto inicial
        root.after(tracking_interval.get() * 1000, track_point)
    else:
        # Detener seguimiento
        track_status_var.set("INACTIVO")
        track_status_label.config(foreground="red")

def track_point():
    """Guarda un punto GPS durante el seguimiento automático"""
    if not running or not tracking.get():
        return
    
    save_point()
    root.after(tracking_interval.get() * 1000, track_point)

def update_saved_points():
    """Actualiza el contador de puntos guardados"""
    csv_file = os.path.join(DATA_DIR, "gps_points.csv")
    if os.path.isfile(csv_file):
        with open(csv_file, 'r') as f:
            # Contar las líneas menos la cabecera
            count = sum(1 for _ in f) - 1
        saved_points_var.set(f"Puntos guardados: {count}")
    else:
        saved_points_var.set("Puntos guardados: 0")

# Variables de datos
data_vars = {
    "Hora Sistema": tk.StringVar(value="--:--:--"),
    "Hora GPS": tk.StringVar(value="--:--:--"),
    "Latitud": tk.StringVar(value="---"),
    "Longitud": tk.StringVar(value="---"),
    "Calidad de Señal": tk.StringVar(value="---"),
    "Satélites en Uso": tk.StringVar(value="---"),
    "Precisión HDOP": tk.StringVar(value="---"),
    "Altitud": tk.StringVar(value="---"),
    "Separación Geoidal": tk.StringVar(value="---")
}

# Variables para estado del GPS
gps_status_var = tk.StringVar(value="Sin datos")
time_since_var = tk.StringVar(value="---")

# Variables para almacenamiento
last_latitude = tk.StringVar(value="---")
last_longitude = tk.StringVar(value="---")
saved_message = tk.StringVar(value="---")

# Variables para el seguimiento
tracking = tk.BooleanVar(value=False)
tracking_interval = tk.IntVar(value=30)  # Intervalo en segundos
track_status_var = tk.StringVar(value="INACTIVO")
saved_points_var = tk.StringVar(value="Puntos guardados: 0")

# Variable para la trama formateada
formatted_message_var = tk.StringVar(value="$---#---@---")

def update_formatted_message():
    """Genera la trama con latitud, longitud y mensaje"""
    lat_value = last_latitude.get()
    lon_value = last_longitude.get()
    message_value = saved_message.get()
    formatted_message_var.set(f"${lat_value}#{lon_value}@{message_value}")

def save_message():
    """Guarda el mensaje ingresado"""
    message = message_text.get("1.0", "end").strip()[:50]
    saved_message.set(message)
    update_formatted_message()
    # Mostrar confirmación
    status_label.config(text="¡Mensaje guardado!")
    # Quitar el mensaje de estado después de 2 segundos
    root.after(2000, lambda: status_label.config(text=""))

# Crear el frame principal
frame = ttk.Frame(root, padding=10)
frame.pack(fill="both", expand=True)

# Crear frame para el estado del GPS (en la parte superior)
gps_status_frame = ttk.Frame(frame, relief="groove", borderwidth=2)
gps_status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

# Indicador de estado del GPS
ttk.Label(gps_status_frame, text="Estado GPS:", font=("Arial", 12, "bold")).pack(side="left", padx=5)
gps_status_label = ttk.Label(gps_status_frame, textvariable=gps_status_var, font=("Arial", 12, "bold"), foreground="red")
gps_status_label.pack(side="left", padx=5)

# Indicador de tiempo desde el último dato
ttk.Label(gps_status_frame, text="Último dato hace:", font=("Arial", 12)).pack(side="left", padx=20)
ttk.Label(gps_status_frame, textvariable=time_since_var, font=("Arial", 12)).pack(side="left")

row = 1  # Empezamos desde la fila 1 ya que la 0 tiene el frame de estado

# Crear etiquetas y campos en la interfaz
for key, var in data_vars.items():
    ttk.Label(frame, text=key + ":", font=("Arial", 16)).grid(row=row, column=0, sticky="w", padx=5, pady=5)
    ttk.Label(frame, textvariable=var, font=("Arial", 16), background="black", foreground="lime", width=20).grid(row=row, column=1, sticky="w", padx=5, pady=5)
    row += 1

# Campo de mensaje
ttk.Label(frame, text="Mensaje (máx 50 caracteres):", font=("Arial", 14)).grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
message_text = tk.Text(frame, font=("Arial", 14), width=50, height=1, wrap="word")
message_text.grid(row=row+1, column=0, columnspan=2, padx=5, pady=5, sticky="w")

# Indicadores de los últimos valores almacenados
ttk.Label(frame, text="Última Latitud (decimal):", font=("Arial", 14)).grid(row=row+2, column=0, sticky="w", padx=5, pady=5)
ttk.Label(frame, textvariable=last_latitude, font=("Arial", 16), background="black", foreground="cyan", width=15).grid(row=row+2, column=1, padx=5, pady=5)

ttk.Label(frame, text="Última Longitud (decimal):", font=("Arial", 14)).grid(row=row+3, column=0, sticky="w", padx=5, pady=5)
ttk.Label(frame, textvariable=last_longitude, font=("Arial", 16), background="black", foreground="cyan", width=15).grid(row=row+3, column=1, padx=5, pady=5)

# Indicador de la trama generada
ttk.Label(frame, text="Trama Generada:", font=("Arial", 14)).grid(row=row+4, column=0, sticky="w", padx=5, pady=5)
ttk.Label(frame, textvariable=formatted_message_var, font=("Arial", 14), background="black", foreground="yellow", width=50).grid(row=row+5, column=0, columnspan=2, padx=5, pady=5, sticky="w")

# Frame para el seguimiento
tracking_frame = ttk.LabelFrame(frame, text="Seguimiento GPS", padding=5)
tracking_frame.grid(row=row+6, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

# Controles de seguimiento
ttk.Label(tracking_frame, text="Intervalo:", font=("Arial", 12)).grid(row=0, column=0, padx=5, pady=5)
ttk.Spinbox(tracking_frame, from_=5, to=3600, increment=5, textvariable=tracking_interval, width=5).grid(row=0, column=1, padx=5, pady=5)
ttk.Label(tracking_frame, text="segundos", font=("Arial", 12)).grid(row=0, column=2, padx=5, pady=5)

ttk.Checkbutton(tracking_frame, text="Activar seguimiento", variable=tracking, command=start_tracking).grid(row=0, column=3, padx=5, pady=5)
ttk.Label(tracking_frame, text="Estado:", font=("Arial", 12)).grid(row=0, column=4, padx=5, pady=5)
track_status_label = ttk.Label(tracking_frame, textvariable=track_status_var, font=("Arial", 12, "bold"), foreground="red")
track_status_label.grid(row=0, column=5, padx=5, pady=5)

# Indicador de puntos guardados
ttk.Label(tracking_frame, textvariable=saved_points_var, font=("Arial", 12)).grid(row=1, column=0, columnspan=6, padx=5, pady=5, sticky="w")

# Etiqueta de estado para confirmaciones
status_label = ttk.Label(frame, text="", font=("Arial", 12, "italic"), foreground="green")
status_label.grid(row=row+7, column=0, columnspan=2, padx=5, pady=5, sticky="w")

# Botones en la misma línea
button_frame = ttk.Frame(root)
button_frame.pack(pady=5)

ttk.Button(button_frame, text="Guardar Mensaje", command=save_message).pack(side="left", padx=5)
ttk.Button(button_frame, text="Guardar Punto", command=save_point).pack(side="left", padx=5)
ttk.Button(button_frame, text="Exportar Datos", command=export_all_points).pack(side="left", padx=5)
ttk.Button(button_frame, text="Salir", command=safe_exit).pack(side="left", padx=5)

# Manejar cierre de ventana
root.protocol("WM_DELETE_WINDOW", safe_exit)

# Inicializar el contador de puntos guardados
update_saved_points()

# Iniciar la lectura de datos del GPS y la actualización del tiempo
root.after(1000, read_gps_data)
root.after(1000, update_time_since_last_data)

# Ejecutar la interfaz
root.mainloop()
