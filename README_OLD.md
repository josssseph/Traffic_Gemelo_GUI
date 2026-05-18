# Traffic Gemelo - Detección de Vehículos y API en Tiempo Real

## Estructura del Proyecto

```
traffic-gemelo/
├── src/
│   ├── detector.py         # Engine YOLOv8 + Tracking + Fallback stream
│   ├── server.py           # Servidor Flask con endpoints API REST
│   ├── buffer_manager.py   # Buffer circular (5s) thread-safe
│   ├── video_codecs.py     # Codificadores (JPEG, WebP, H264, Adaptativo)
│   ├── preprocessing.py    # Filtros de imagen (denoise, contraste, etc)
│   └── codecs.py           # (Módulo auxiliar)
├── models/                 # Modelos YOLO (descargados automáticamente)
├── videos/                 # Videos locales de fallback
│   └── respaldo.mp4        # Respaldo para cuando stream falla
├── requirements.txt        # Dependencias Python
├── run.py                  # Script principal (inicia detector + servidor)
├── tune.py                 # Herramienta de tuning interactiva
├── README.md               # Este archivo
├── TUNING_GUIDE.md         # Guía detallada de optimización
└── SHUTDOWN_GUIDE.md       # Procedimiento de shutdown seguro
```

## Requisitos de Hardware y Software

- **GPU NVIDIA**: RTX 2060 o superior (con drivers NVIDIA instalados)
- **CUDA 12.1**: Instalado y funcional
- **Python 3.10+** (Ubuntu 24.04 recomendado)
- **ffmpeg**: Para descargar y procesar videos

## Instalación (Pasos Realizados)

### 1. Preparar Drivers NVIDIA
```bash
# Verificar drivers disponibles
ubuntu-drivers devices | grep recommended

# Instalar drivers recomendados
sudo ubuntu-drivers autoinstall

# Reiniciar
sudo reboot

# Verificar instalación
nvidia-smi
```

**Output esperado:** Debe mostrarse tu GPU (ej: NVIDIA GeForce RTX 2060) con versión de CUDA.

### 2. Crear Entorno Virtual
```bash
mkdir traffic-gemelo
cd traffic-gemelo

# Crear venv
python3 -m venv venv
source venv/bin/activate

# Actualizar pip
pip install --upgrade pip
```

### 3. Instalar PyTorch con CUDA 12.1
```bash
# PyTorch estable con soporte CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 4. Instalar Dependencias del Proyecto
```bash
pip install ultralytics opencv-python flask flask-cors requests
```

### 5. Generar requirements.txt
```bash
pip freeze > requirements.txt
```

### 6. Verificar CUDA
```bash
python -c "import torch; print('CUDA disponible:', torch.cuda.is_available())"
```

**Debe retornar:** `CUDA disponible: True`

### 7. Crear Estructura de Directorios
```bash
mkdir -p ~/traffic-gemelo/src
mkdir -p ~/traffic-gemelo/models
mkdir -p ~/traffic-gemelo/videos
```

### 8. Descargar Video de Respaldo
```bash
# Testear el stream en vivo (opcional)
ffplay "https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8"

# Descargar 120 segundos de video como respaldo
ffmpeg -i "https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8" -t 120 -c copy ~/traffic-gemelo/videos/respaldo.mp4
```

**Nota:** Si el enlace del stream no funciona, busca alternativas en [Caltrans](https://cwwp2.dot.ca.gov/) o [TRAFICAM](https://traficam.dot.ca.gov/).

### 9. Modelo YOLOv8 (Se descarga automáticamente)
```bash
# Primera ejecución descargará yolov8n.pt (~6MB)
python -c "from ultralytics import YOLO; model = YOLO('yolov8n.pt'); print('✓ Modelo descargado')"
```

## Ejecución

### Paso 1: Activar entorno virtual
```bash
cd ~/traffic-gemelo
source venv/bin/activate
```

### Paso 2: Ejecutar el servidor (Opción Recomendada)
```bash
python run.py
```

**Output esperado:**
```
============================================================
TRAFFIC GEMELO - Detection & API Server
============================================================
[1] Cargando modelo YOLOv8 en GPU...
[2] Iniciando hilo de detección...
[3] Levantando servidor Flask en http://0.0.0.0:5000

Endpoints disponibles:
  GET http://localhost:5000/detections
  GET http://localhost:5000/health

Presiona Ctrl+C para detener.
============================================================

[LIVE] Vehicles: 3 | Congestion: MEDIUM | Density: 0.0082
[LIVE] Vehicles: 5 | Congestion: HIGH | Density: 0.0125
```

### Alternativa: Ejecución directa del servidor
```bash
python src/server.py
```

**Primera ejecución:** Puede tomar 30-60 segundos mientras descarga el modelo YOLOv8 (~6MB).

## Testing de la API

### Endpoints Disponibles

#### 1. Dashboard Web Interactivo (Recomendado)
```bash
# Abrir en navegador
http://localhost:5000/
```

**Características:**
- ✅ Video anotado en vivo (izquierda)
- ✅ Detecciones en tiempo real (derecha)
- ✅ KPIs: Total vehículos, Congestión, Densidad
- ✅ Conteos por tipo de vehículo
- ✅ JSON completo actualizado cada 500ms
- ✅ Responsive para móviles
- ✅ Colores por tipo: Naranja (cars), Verde (buses), Rojo (trucks)
- ✅ Toggle para cambiar entre LIVE y FALLBACK sin reinicio

#### 2. Stream MJPEG (Video en vivo)
```bash
# Usar en herramientas de video o embebido en web
http://localhost:5000/video_feed
```

**Características:**
- ✅ Transmisión en tiempo real MJPEG (16 FPS sincronizado)
- ✅ Bounding boxes anotados
- ✅ IDs de tracking
- ✅ Velocidades en px/s
- ✅ FPS en pantalla
- ✅ Status stream (LIVE/FALLBACK)
- ✅ **SIN LAG** - Preprocessing optimizado por defecto

#### 3. API JSON
```bash
# Obtener detecciones actuales (desde cualquier PC en la red)
curl -s http://localhost:5000/detections | jq .

# Health check
curl -s http://localhost:5000/health | jq .

# Monitoreo en tiempo real desde otra terminal/PC
watch -n 0.5 'curl -s http://192.168.1.X:5000/detections | jq .'
```

### Respuesta JSON Completa
```json
{
  "timestamp": 1715200000.0,
  "status_stream": "live",
  "counts": {
    "car": 3,
    "bus": 1,
    "truck": 0,
    "motorcycle": 0,
    "bicycle": 0
  },
  "total": 4,
  "density": 0.0082,
  "congestion": "MEDIUM",
  "vehicles": [
    {
      "id": 101,
      "type": "car",
      "bbox": [100, 50, 200, 150],
      "speed_px": 45.3,
      "confidence": 0.92
    },
    {
      "id": 102,
      "type": "bus",
      "bbox": [300, 80, 450, 200],
      "speed_px": 38.5,
      "confidence": 0.88
    }
  ]
}
```

**Campos del JSON:**
- `timestamp`: Unix timestamp de cuando se procesó el frame
- `status_stream`: `"live"` (stream .m3u8) o `"fallback loop"` (video local en bucle)
- `counts`: Cantidad de vehículos por tipo
- `total`: Total de vehículos detectados
- `density`: Densidad calculada (vehículos/20)
- `congestion`: Nivel de congestión (LOW/MEDIUM/HIGH/CRITICAL)
- `vehicles`: Lista detallada de cada vehículo con ID, tipo, bounding box, velocidad y confianza

## Detalles Técnicos de Implementación

### detector.py (320+ líneas, Fase Producción - OPTIMIZADO)

**Funcionalidades Principales:**
- ✅ Stream .m3u8 en vivo desde DOT California
- ✅ Fallback automático a video local con **bucle infinito**
- ✅ YOLOv8 Nano acelerado por CUDA (RTX 2060+)
- ✅ Tracking robusto de vehículos con IDs únicos
- ✅ **THROTTLE AUTOMÁTICO a 16 FPS** - Sincroniza video local (30 FPS) a 16 FPS para evitar desborde de buffer
- ✅ Cálculo de velocidad en píxeles/frame basado en desplazamiento de centroide
- ✅ Cálculo automático de densidad y nivel de congestión
- ✅ Anotaciones visuales completas (bounding boxes, IDs, velocidades, FPS, status)
- ✅ Thread-safe con locks para lectura concurrente desde Flask
- ✅ Gestión de memoria eficiente con `frame_lock` + `data_lock`

**Clases de Vehículos Detectados (YOLO COCO):**
| Tipo | Clase ID | Color | Estado |
|------|----------|-------|--------|
| car | 2 | Naranja | ✅ Detectado |
| bus | 5 | Verde | ✅ Detectado |
| truck | 7 | Rojo | ✅ Detectado |
| motorcycle | 3 | Cian | ✅ Detectado |
| bicycle | 1 | Azul | ✅ Detectado |

**Niveles de Congestión (Basado en cantidad de vehículos):**
| Vehículos | Nivel |
|-----------|-------|
| 0-3 | LOW |
| 4-7 | MEDIUM |
| 8-12 | HIGH |
| 13+ | CRITICAL |

**Optimizaciones Implementadas:**
- ✅ **Throttle de FPS**: Limita captura a 16 FPS máximo (evita buffer desbordado con video local a 30 FPS)
- ✅ **Procesamiento selectivo**: 1 de cada 2 frames para detección (8 FPS), el resto para tracking
- ✅ **GPU optimization**: `verbose=False` en YOLO, CUDA mode, batch processing
- ✅ **Memory management**: Copia de frames, deque con maxlen, FPS history con 30 frames
- ✅ **Variable global `current_output_frame`** con `frame_lock` para acceso thread-safe

**Cambios Recientes (Fase de Optimización):**
- ✅ Agregado sistema de **throttle por tiempo** para sincronizar video a 16 FPS
- ✅ Buffer ahora permanece consistentemente en **5 segundos** (no fluctúa entre 2-14s)
- ✅ Video local ya no desborda el buffer
- ✅ FPS real más estable (~14.5 FPS consistentes)

### server.py (350+ líneas, Fase Producción)

**Endpoints REST Disponibles:**

| Endpoint | Método | Descripción | Respuesta |
|----------|--------|-------------|----------|
| `/` | GET | Dashboard web interactivo (HTML5 + AJAX) | HTML |
| `/video_feed` | GET | Stream MJPEG anotado en tiempo real | Video MJPEG |
| `/detections` | GET | API JSON con detecciones actuales | JSON |
| `/health` | GET | Health check del servidor | JSON |
| `/codec/config` | GET | Configuración actual del codec | JSON |
| `/codec/switch/<type>/<quality>` | POST | Cambiar codec en tiempo real | JSON |
| `/preprocessing/switch/<preset>` | POST | Cambiar preprocessing en tiempo real | JSON |
| `/buffer/stats` | GET | Estadísticas del buffer (5s) | JSON |
| `/stream/status` | GET | Estado actual (LIVE o FALLBACK) | JSON |
| `/stream/switch/<mode>` | POST | Cambiar stream sin reinicio | JSON |

**Nuevos Endpoints Agregados:**
- ✅ `/preprocessing/switch/<preset>` - Cambiar entre 'quality', 'balanced', 'fast', 'none' en tiempo real

**Dashboard Web:**
- Interfaz moderna con tema oscuro
- Stream MJPEG en vivo (izquierda)
- Datos de detección en tiempo real (derecha)
- KPIs: Total vehículos, Congestión, Densidad
- Tabla expandible de vehículos detectados
- Toggle para cambiar entre LIVE y FALLBACK
- Responsive (móviles, tablets, desktops)
- Manejo robusto de errores

**Sistema de Codec:**
- Cambio de codec SIN reinicio del servidor
- Soporta: JPEG, WebP, H264, Adaptativo
- Estadísticas en tiempo real de compresión

**Generador MJPEG (generate_frames):**
- Lee SOLO el frame más reciente del buffer
- Encoding dinámico con codec activo
- Retry automático (máximo 30 errores)
- Sincronización a 16 FPS
- Headers HTTP compatibles universales
- **Preprocessing DESACTIVADO por defecto** - Default: 'none' para máxima velocidad

**Configuración del Servidor:**
- Host: `0.0.0.0` (acepta conexiones en todas las interfaces)
- Puerto: `5000` (configurable en run.py)
- CORS habilitado
- Servidor multihilo: `threaded=True`
- Modo debug: Deshabilitado en producción

### buffer_manager.py (150+ líneas)

**Propósito:** Almacenamiento circular thread-safe de frames crudos

**Características:**
- Buffer circular automático: mantiene exactamente 5 segundos de video (80 frames @ 16 FPS)
- Thread-safe con `threading.RLock()` para acceso concurrente
- Métodos de consulta:
  - `get_latest()` → Frame más reciente (usado por streaming)
  - `get_by_index(idx)` → Frame por posición (0=antiguo, -1=reciente)
  - `get_by_timestamp(ts)` → Frame más cercano a un timestamp
  - `get_range(start, end)` → Rango de frames (para batch processing)
  - `get_all()` → Todos los frames actuales

**Estadísticas Disponibles (GET `/buffer/stats`):**
```json
{
  "total_frames_ever": 42505,
  "current_frames": 80,
  "max_capacity": 80,
  "buffer_duration_seconds": 5.0,
  "oldest_timestamp": 1715200000.1234,
  "newest_timestamp": 1715200005.6789
}
```

**Singleton Global:**
```python
buffer_manager = BufferManager(buffer_duration_seconds=5, expected_fps=16)
```

### video_codecs.py (400+ líneas)

**Codecs Soportados:**

| Codec | Compresión | Velocidad | Uso | Calidad |
|-------|-----------|----------|-----|---------|
| **JPEG** | Media | Rápida | Default, compatible universal | Estándar |
| **WebP** | Alta | Media | Mejor relación calidad/tamaño | Mejor |
| **H264** | Muy Alta | Lenta | Archivos (batch processing) | Variable |
| **Adaptativo** | Variable | Variable | Auto-selección según carga | Variable |

**Interfaz Común:**
```python
codec = get_active_codec()
frame_bytes = codec.encode(frame)  # bytes JPEG/WebP
stats = codec.get_stats()  # estadísticas
```

**Cambiar Codec en Tiempo Real (SIN reinicio):**
```bash
# JPEG calidad 90
curl -X POST http://localhost:5000/codec/switch/jpeg/90

# WebP calidad 85
curl -X POST http://localhost:5000/codec/switch/webp/85

# Ver config actual
curl http://localhost:5000/codec/config | jq
```

**Cambiar Preprocessing en Tiempo Real:**
```bash
# SIN filtros (máximo rendimiento - DEFAULT)
curl -X POST http://localhost:5000/preprocessing/switch/none

# Con filtros moderados (balanceado)
curl -X POST http://localhost:5000/preprocessing/switch/balanced

# Con filtros agresivos (máxima calidad, LENTO)
curl -X POST http://localhost:5000/preprocessing/switch/quality

# Solo resize (rápido, reduce resolución)
curl -X POST http://localhost:5000/preprocessing/switch/fast
```

**Configuración Global (video_codecs.py):**
```python
CODEC_CONFIG = {
    'active_codec': 'jpeg',           # 'jpeg', 'webp', 'h264', 'adaptive'
    'quality': 80,                    # 1-100
    'preprocessing': 'none',          # DEFAULT: SIN filtros para evitar lag
    'target_fps': 16,                 # Sincronización
    'resize_factor': 1.0,             # 1.0=full, 0.8=80%, etc
}
```

**Cambio de Default (Optimización):**
- **Antes**: `'preprocessing': 'balanced'` (aplicaba CLAHE + Bilateral + Unsharp = PESADO)
- **Ahora**: `'preprocessing': 'none'` (sin filtros = RÁPIDO)
- **Resultado**: Sin lag en streaming, sin ventiladores sonando constantemente

### preprocessing.py (250+ líneas)

**Propósito:** Pipeline de filtros de imagen pre-encoding (OPCIONAL)

**Filtros Disponibles:**
- `denoise()` - Bilateral filter (suaviza sin perder bordes)
- `enhance_contrast()` - CLAHE (Contrast Limited Adaptive Histogram Equalization) ⚠️ **COSTOSO**
- `sharpen()` - Unsharp mask (aumenta nitidez)
- `brightness_contrast()` - Ajuste manual
- `color_correction()` - Control de saturación
- `resize()` - Redimensionamiento
- `adaptive_histogram()` - Ecualización adaptativa

**Presets Predefinidos:**
| Preset | Contenido | Rendimiento | Uso |
|--------|-----------|-------------|-----|
| `'none'` | Sin filtros | MUY RÁPIDO ✅ | **DEFAULT - Streaming sin lag** |
| `'quality'` | Denoise + CLAHE + Sharpen | LENTO ❌ | Máxima claridad visual |
| `'balanced'` | Denoise + CLAHE + Sharpen | PESADO ❌ | Balance visual |
| `'fast'` | Solo resize | RÁPIDO ✅ | Máxima velocidad con compresión |

**⚠️ IMPORTANTE - Cambio Crítico:**

El preprocessing **'balanced'** y **'quality'** aplican **CLAHE** (Contrast Limited Adaptive Histogram Equalization), que es:
- O(n²) en complejidad computacional
- Histogramas por región de la imagen
- **Muy costoso en GPU/CPU**
- **Causa lag severo en streaming**

**Solución implementada:**
- Default ahora es `'none'` (sin filtros)
- Si necesitas filtros, cambiar via `/preprocessing/switch/<preset>`
- Alternativamente, usar `'fast'` (solo resize, mucho más rápido)

**Cuando usar cada preset:**
- `'none'`: SIEMPRE en streaming en vivo (default)
- `'fast'`: Si quieres comprimir resolución sin lag
- `'balanced'`: SIN usar en tiempo real (batch processing)
- `'quality'`: SIN usar en tiempo real (post-processing)

### tune.py (200+ líneas)

**Propósito:** Herramienta CLI interactiva para tuning en TIEMPO REAL

**Requisito:** El servidor debe estar corriendo (`python run.py`)

**Uso:**
```bash
python tune.py
```

**Menú de Opciones:**
```
1. Ver configuración actual
2. Ver estadísticas del codec
3. Ver estadísticas del buffer
4. Cambiar a JPEG (ajustar calidad)
5. Cambiar a WebP (mejor compresión)
6. Cambiar a Perfil "Máxima Calidad" (JPEG 95 + quality preset)
7. Cambiar a Perfil "Balance" (JPEG 80 + balanced preset)
8. Cambiar a Perfil "Máxima Velocidad" (JPEG 60 + none preset)
9. Cambiar Preprocessing (quality/balanced/fast/none) ← NUEVO
0. Salir
```

**Opción 9 - Cambiar Preprocessing en Tiempo Real:**
```
Opciones de Preprocessing:
  1. quality    - Filtros agresivos (máxima calidad, LENTO)
  2. balanced   - Filtros moderados (PESADO)
  3. fast       - Solo resize (RÁPIDO)
  4. none       - Sin filtros (MÁS RÁPIDO - RECOMENDADO)
```

**Cambios Recientes:**
- ✅ Agregada función `switch_preprocessing(preset)`
- ✅ Agregada opción #9 para cambiar preprocessing
- ✅ Perfiles ahora aplican preprocessing correctamente
- ✅ Mejor feedback visual de cambios

**Ejemplo de Uso:**
```bash
# Terminal 1: Inicia servidor
python run.py

# Terminal 2: Abre herramienta de tuning
python tune.py

# Elige opción 8 (Máxima Velocidad)
# Verifica que video fluye sin lag ✅
# Elige opción 9 y luego 1 (quality preset)
# Verifica que se aplican filtros correctamente
```

7. Dashboard HTML actualiza cada 500ms vía AJAX

### URL del Stream en Vivo
```
https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8
```

**Ubicación:** Brookhurst Ave, Anaheim, CA (cruce de carreteras principal)

Si el stream es inaccesible, buscar alternativas en:
- [Caltrans QuickMap](https://cwwp2.dot.ca.gov/)
- [TrafiCam](https://traficam.dot.ca.gov/)

## Solución de Problemas

### ❌ Error: ModuleNotFoundError: No module named 'torch'
```
ModuleNotFoundError: No module named 'torch'
```
**Solución:** Asegurar que el venv está activado:
```bash
source venv/bin/activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### ❌ Error: CUDA out of memory
```
RuntimeError: CUDA out of memory: tried to allocate X.XXGiB
```
**Solución:**
1. Usar modelo más pequeño (yolov8n.pt es el más ligero, ya se usa)
2. Reducir resolución del video
3. Reiniciar el servidor para limpiar memoria:
```bash
pkill -f "python run.py"
python run.py
```

### ❌ Error: Stream .m3u8 no abre
```
[FALLBACK] Stream https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8 failed.
[FALLBACK] Using local video: /home/user/traffic-gemelo/videos/respaldo.mp4
```
**Comportamiento:** ✅ **Es NORMAL**. El sistema automáticamente switchea al video local.

**Verificar:**
```bash
ls -lh ~/traffic-gemelo/videos/respaldo.mp4
```
Si no existe o es muy pequeño:
```bash
ffmpeg -i "https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8" -t 120 -c copy ~/traffic-gemelo/videos/respaldo.mp4
```

### ❌ Error: "Address already in use" en puerto 5000
```
OSError: [Errno 48] Address already in use
```
**Solución:** Matar proceso anterior:
```bash
lsof -i :5000 | grep -v PID | awk '{print $2}' | xargs kill -9
python run.py
```

O usar puerto diferente (editar `run.py`):
```python
start_server(host='0.0.0.0', port=5001, debug=False)  # Cambiar 5000 a 5001
```

### ❌ Error: "CUDA disponible: False"
```python
python -c "import torch; print('CUDA disponible:', torch.cuda.is_available())"
# Output: CUDA disponible: False  ❌
```
**Solución:**
1. Verificar drivers NVIDIA:
   ```bash
   nvidia-smi
   ```
   Si no muestra tu GPU, instalar drivers:
   ```bash
   ubuntu-drivers devices
   sudo ubuntu-drivers autoinstall
   sudo reboot
   ```

2. Reinstalar PyTorch con CUDA 12.1:
   ```bash
   pip uninstall torch torchvision torchaudio
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```

3. Verificar nuevamente:
   ```bash
   nvidia-smi
   python -c "import torch; print(torch.cuda.is_available())"  # Debe ser True
   ```

### ⚠️ La detección es lenta o laggy
**Causas y soluciones:**

| Síntoma | Causa | Solución |
|---------|-------|----------|
| API responde lento | GPU no se está usando | Verificar con `nvidia-smi` mientras se ejecuta |
| Muchos fotogramas perdidos | Procesamiento demasiado lento | Aumentar skip de frames en detector.py (línea ~95) |
| Calor excesivo en GPU | Carga muy alta | Reducir resolución de entrada |

Monitorear GPU en tiempo real:
```bash
watch -n 0.5 nvidia-smi
```

### 📹 Mejorar video de respaldo
Descargar más tiempo:
```bash
# Descargar 5 minutos (300 segundos)
ffmpeg -i "https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8" -t 300 -c copy ~/traffic-gemelo/videos/respaldo.mp4
```

Comprimir para ahorrar espacio:
```bash
# Reducir a 1280x720, 24fps, bitrate bajo
ffmpeg -i ~/traffic-gemelo/videos/respaldo.mp4 -vf scale=1280:720 -r 24 -b:v 2M ~/traffic-gemelo/videos/respaldo_compressed.mp4
mv ~/traffic-gemelo/videos/respaldo_compressed.mp4 ~/traffic-gemelo/videos/respaldo.mp4
```

## Formatos de Video Soportados

**OpenCV (cv2.VideoCapture) soporta:**

| Formato | Extensión | Estado | Codec |
|---------|-----------|--------|-------|
| **MP4** | `.mp4` | ✅ Soportado | H.264, H.265 |
| **MOV** | `.mov` | ✅ Soportado | H.264, ProRes |
| **AVI** | `.avi` | ✅ Soportado | MJPEG, MPEG-4 |
| **MKV** | `.mkv` | ✅ Soportado | VP8, VP9, H.264 |
| **WebM** | `.webm` | ✅ Soportado | VP8, VP9 |
| **M3U8** | `.m3u8` | ✅ Soportado | HLS Streaming |

### Usar archivo .MOV

Tu archivo `.mov` funciona sin problemas:

```bash
# Simplemente copia a carpeta de videos
cp tu_video.mov ~/traffic-gemelo/videos/respaldo.mov

# O usa ffmpeg para convertir a MP4 (más compatible):
ffmpeg -i video.mov -c:v libx264 -c:a aac video.mp4
```

**El código detecta automáticamente** si existe `.mp4` o `.mov` y usa el disponible.

## Integración con Equipo de Desarrollo (Dev B y Dev C)

El JSON expuesto en `/detections` es el **contrato de datos** central que permite trabajar en paralelo.

### Para Dev B (Middleware TraCI - Simulación en SUMO)

Desde PC 2, conectarse al servidor JSON de PC 1:

```python
import requests
import time

# Configuración
PC1_IP = "192.168.1.10"  # Cambiar con tu IP
API_URL = f"http://{PC1_IP}:5000/detections"

while True:
    try:
        response = requests.get(API_URL, timeout=1)
        data = response.json()
        
        # Usar datos para inyectar en SUMO
        total_vehicles = data['total']
        congestion = data['congestion']
        vehicles = data['vehicles']
        
        print(f"Vehículos: {total_vehicles} | Congestión: {congestion}")
        
        # Para cada vehículo:
        for vehicle in vehicles:
            vehicle_id = f"real_{vehicle['id']}"
            x, y = vehicle['bbox'][:2]  # Píxeles
            
            # PRÓXIMO: Convertir píxeles a coordenadas SUMO
            # sumo_x, sumo_y = pixel_to_sumo(x, y)
            # traci.vehicle.moveTo(vehicle_id, sumo_x, sumo_y)
        
        # Detectar colisiones (bounding boxes que se tocan)
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                v1_bbox = vehicles[i]['bbox']  # [x1, y1, x2, y2]
                v2_bbox = vehicles[j]['bbox']
                
                # Checar solapamiento
                if (v1_bbox[0] < v2_bbox[2] and v1_bbox[2] > v2_bbox[0] and
                    v1_bbox[1] < v2_bbox[3] and v1_bbox[3] > v2_bbox[1]):
                    print(f"⚠️  COLISIÓN: {vehicles[i]['type']} (ID {vehicles[i]['id']}) "
                          f"vs {vehicles[j]['type']} (ID {vehicles[j]['id']})")
        
        time.sleep(0.2)  # Consultar cada 200ms
    except Exception as e:
        print(f"Error conectando: {e}")
        time.sleep(1)
```

### Conversión de Píxeles a Coordenadas SUMO

**Paso 1: Calibración (hacer UNA SOLA VEZ)**

Mira el video y mide algo conocido:
- Ancho de carril (típicamente 3.5m)
- Longitud de vehículo (típicamente 4.5m)
- Espaciado de líneas peatonales

**Ejemplo de cálculo:**
```
Si un carril mide 140 píxeles en el video:
pixels_per_meter = 140 / 3.5 = 40 píxeles/metro
```

**Paso 2: Usar en conversión**

```python
def pixel_to_sumo(center_x_px, center_y_px, frame_height=720):
    """Convertir píxeles de video a coordenadas SUMO"""
    pixels_per_meter = 40  # ← CALIBRAR según tu video
    map_origin_x = 0       # Origen del mapa SUMO
    map_origin_y = 0       # Origen del mapa SUMO
    
    # Convertir a metros (invertir Y porque video usa Y invertida)
    world_x = map_origin_x + (center_x_px / pixels_per_meter)
    world_y = map_origin_y + ((frame_height - center_y_px) / pixels_per_meter)
    
    return world_x, world_y

def speed_px_to_ms(speed_px, fps=16):
    """Convertir velocidad píxeles/frame a m/s y km/h"""
    pixels_per_meter = 40  # ← MISMO VALOR
    speed_px_per_s = speed_px * fps
    speed_ms = speed_px_per_s / pixels_per_meter
    speed_kmh = speed_ms * 3.6
    return speed_ms, speed_kmh
```

**Paso 3: Inyectar en SUMO**

```python
import traci

for vehicle in data['vehicles']:
    vehicle_id = f"real_{vehicle['id']}"
    center_x = (vehicle['bbox'][0] + vehicle['bbox'][2]) / 2
    center_y = (vehicle['bbox'][1] + vehicle['bbox'][3]) / 2
    
    sumo_x, sumo_y = pixel_to_sumo(center_x, center_y)
    speed_ms, speed_kmh = speed_px_to_ms(vehicle['speed_px'])
    
    # Crear o actualizar vehículo en SUMO
    try:
        traci.vehicle.add(vehicle_id, "route_id", typeID="passenger")
    except:
        pass  # Ya existe
    
    # Establecer posición y velocidad
    traci.vehicle.moveTo(vehicle_id, sumo_x, sumo_y)
    traci.vehicle.setSpeed(vehicle_id, speed_ms)
```

### Para Dev C (Dashboard - Visualización en Streamlit)

Desde cualquier máquina en la red local:

```python
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

PC1_IP = "192.168.1.10"
API_URL = f"http://{PC1_IP}:5000/detections"

st.set_page_config(page_title="Traffic Dashboard", layout="wide")
st.title("🚗 Traffic Gemelo - Real-time Dashboard")

col1, col2, col3 = st.columns(3)

while True:
    response = requests.get(API_URL)
    data = response.json()
    
    with col1:
        st.metric("Total Vehículos", data['total'])
    with col2:
        st.metric("Congestión", data['congestion'])
    with col3:
        st.metric("Densidad", f"{data['density']:.4f}")
    
    df = pd.DataFrame(data['vehicles'])
    st.dataframe(df)
    
    st.plotly_chart(go.Figure(
        data=[go.Bar(x=list(data['counts'].keys()), y=list(data['counts'].values()))]
    ))
    
    time.sleep(1)
```

### Configuración de Red Local (Paso Importante)

Para que Dev B y Dev C accedan desde otra máquina:

1. **Encontrar IP de PC1:**
   ```bash
   hostname -I
   # Output: 192.168.1.10 (puede variar)
   ```

2. **Verificar conectividad desde PC2:**
   ```bash
   ping 192.168.1.10
   curl http://192.168.1.10:5000/detections
   ```

3. **Si no conecta, verificar firewall:**
   ```bash
   sudo ufw allow 5000
   ```

4. **Usar en scripts de Dev B y Dev C:**
   ```python
   PC1_IP = "192.168.1.10"  # Reemplazar con tu IP real
   API_URL = f"http://{PC1_IP}:5000/detections"
   ```

## Logs y Debugging

### Salida estándar del detector

El detector imprime progreso cada 30 frames procesados:

```
[LIVE] Vehicles: 5 | Congestion: HIGH | Density: 0.0125
[LIVE] Vehicles: 3 | Congestion: MEDIUM | Density: 0.0082
[FALLBACK] Vehicles: 2 | Congestion: LOW | Density: 0.0041
```

### Habilitar debugging más detallado

Editar `src/detector.py` alrededor de la línea ~95 para agregar:

```python
if frame_count % 30 == 0:
    print(f"[DEBUG] Frame {frame_count} | Boxes detectadas: {len(results[0].boxes)}")
    print(f"[DEBUG] Tracking IDs: {[int(b.id) for b in results[0].boxes if b.id]}")
    print(f"...")
```

### Monitorear GPU durante ejecución

En otra terminal:
```bash
# Ver uso de GPU en tiempo real
watch -n 0.5 nvidia-smi

# Ver solo información de proceso
nvidia-smi --query-processes=pid,process_name,gpu_memory_usage --format=csv
```

### Verificar logs de Flask

El servidor Flask imprime requests:
```
127.0.0.1 - - [11/May/2026 19:30:45] "GET /detections HTTP/1.1" 200 -
```

Para más detalle, editar `run.py`:
```python
start_server(host='0.0.0.0', port=5000, debug=True)  # Cambiar debug a True
```

⚠️ **Nota:** `debug=True` recarga el servidor automáticamente si hay cambios en archivos.

## Próximos Pasos

### Fase 1 - ✅ COMPLETADA (Con Visualización)
- [x] Servidor headless con JSON limpio
- [x] Anotaciones visuales en OpenCV
- [x] Stream MJPEG en vivo
- [x] Dashboard web integrado
- [x] Colores dinámicos por tipo de vehículo
- [x] FPS en pantalla
- [x] Bucle automático del video de respaldo

### Fase 2: Middleware TraCI (Dev B) 🔄 PRÓXIMO

Crear `src/traci_middleware.py` que:
1. Consulte `http://192.168.1.10:5000/detections` cada 200ms
2. Inyecte vehículos dinámicamente en SUMO usando `traci.vehicle.add()`
3. Implemente lógica semafórica: si `total > 10`, activar programa `tl_emergency`
4. Sincronice la simulación temporal con el detector
5. Reporte métricas de SUMO de vuelta al sistema

**Instalación SUMO (Dev B):**
```bash
sudo apt-get install sumo sumo-tools
```

**Archivo esperado:** `/src/traci_middleware.py`

**Script de test:**
```python
import requests
import time

while True:
    try:
        data = requests.get('http://192.168.1.10:5000/detections').json()
        print(f"Vehículos: {data['total']} | Congestión: {data['congestion']}")
        # Aquí: lógica TraCI
        time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
```

### Fase 3: Dashboard Avanzado (Dev C) 🔄 PRÓXIMO

Crear `dashboard.py` (Streamlit) que:
1. Consulte `/detections` en tiempo real
2. Muestre gráficos avanzados:
   - Línea temporal de densidad
   - Histograma de velocidades
   - Mapa de calor de detecciones
3. Estadísticas: min/max/avg velocidades, densidad pico
4. Tabla interactiva de vehículos activos
5. Alertas de congestión crítica

**Instalación Streamlit:**
```bash
pip install streamlit plotly pandas numpy
```

**Ejecución:**
```bash
streamlit run dashboard.py
```

### Fase 4: Calibración y Optimización 🔄 PRÓXIMO

1. **Calibración de velocidad:** Convertir `speed_px` a `m/s`
   - Usar referencia conocida (ancho de carril, longitud de vehículo)
   - Fórmula: `speed_ms = speed_px * fps / pixels_per_meter`

2. **Ajuste de modelos:** Testear con yolov8s.pt si se necesita mayor accuracy

3. **Modo predictivo:** Cuando el stream falla, usar SUMO para predecir movimientos futuros

4. **Almacenamiento:** Guardar detecciones en base de datos (SQLite / PostgreSQL)

---

## Resumen de Estado del Proyecto

### ✅ Completado (Fase 1 - Percepción Mejorada)
- [x] Instalación de drivers NVIDIA y CUDA 12.1
- [x] Creación de entorno virtual Python
- [x] Instalación de PyTorch + ultralytics + OpenCV
- [x] Descarga de video de respaldo (respaldo.mp4)
- [x] **detector.py** - YOLOv8 con anotaciones visuales y bucle video
- [x] **server.py** - Flask con MJPEG y dashboard web
- [x] **run.py** - Script de ejecución
- [x] Documentación completa

### 🔄 En Desarrollo
- [ ] Fase 2: Middleware TraCI (Dev B)
- [ ] Fase 3: Dashboard Avanzado Streamlit (Dev C)
- [ ] Fase 4: Calibración y Base de Datos

### 📦 Estructura Actual
```
traffic-gemelo/
├── src/
│   ├── detector.py           ✅ (180+ líneas, con visualización)
│   └── server.py             ✅ (150+ líneas, con MJPEG + web)
├── videos/
│   └── respaldo.mp4          ✅ (Video local en bucle)
├── models/                   📦 (Se llena al ejecutar)
├── requirements.txt          ✅ (Actualizado)
├── run.py                    ✅ (Listo)
└── README.md                 ✅ (Este archivo)
```

### 🎯 Características Implementadas
- ✅ **Percepción:** YOLOv8 + CUDA con tracking
- ✅ **Anotaciones:** Bounding boxes, IDs, velocidades, FPS
- ✅ **Resilencia:** Fallback automático + bucle video
- ✅ **API:** JSON limpio para SUMO (Fase 2)
- ✅ **Visualización:** MJPEG + Dashboard web moderno
- ✅ **Red:** Preparado para arquitectura distribuida

### 📊 Rendimiento Esperado
- **Detección:** 20-30 FPS en RTX 2060
- **API Response:** < 50ms
- **Latencia Video Web:** 500-800ms
- **Throughput JSON:** 2-5 requests/segundo

---

**Versión**: 1.2 (Con Visualización) | **Última actualización**: 11 de Mayo de 2026

**Autor**: Equipo de Visión Computacional | **Hardware**: MSI GE63 (RTX 2060) + Lenovo (SUMO)
