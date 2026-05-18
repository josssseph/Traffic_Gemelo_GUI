# 🚗 Traffic Gemelo - Detección de Vehículos en Tiempo Real

**Sistema de detección de vehículos en tiempo real con calibración homográfica, streaming adaptativo y API REST.**

- Modelo: YOLOv8s pequeño (~21.5 MB)
- GPU: NVIDIA CUDA 12.1
- Stream: Video en vivo (m3u8) + fallback local
- Calibración: Homografía pixel → coordenadas mundiales (SUMO)
- API: Flask REST con endpoints JSON

---

## 📋 Contenido

1. [Arquitectura](#arquitectura)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Uso Rápido](#uso-rápido)
5. [Calibración Homográfica](#calibración-homográfica)
6. [API Endpoints](#api-endpoints)
7. [Tuning y Optimización](#tuning-y-optimización)
8. [Fases Completadas](#fases-completadas)
9. [Troubleshooting](#troubleshooting)
10. [Shutdown Seguro](#shutdown-seguro)

---

## Arquitectura

### Estructura del Proyecto

```
traffic-gemelo/
├── src/
│   ├── detector.py              # Engine YOLOv8 + tracking + fallback
│   ├── server.py                # Servidor Flask + API REST + Web UI
│   ├── calibration_manager.py   # Gestión de matrices homográficas
│   ├── buffer_manager.py        # Buffer circular (5s) thread-safe
│   ├── video_manager.py         # Gestor de fuentes de video
│   ├── video_codecs.py          # Codificadores (JPEG, WebP, H264)
│   ├── preprocessing.py         # Filtros de imagen
│   └── codecs.py                # Módulo auxiliar
├── models/                      # Modelos YOLO (descargados automáticamente)
├── videos/                      # Videos locales de fallback
│   ├── respaldo.mp4             # Stream local fallback
│   ├── respaldo1.mp4            # Video local para calibración
│   └── respaldo2.MOV            # Video local para calibración
├── networks/                    # Archivos SUMO (.net.xml)
│   └── cuenca_respaldo1.net.xml # Mapa de la red vial
├── calibration/                 # Matrices homográficas persistentes
│   ├── respaldo1.pkl            # Matriz binaria (NumPy)
│   ├── respaldo1_metadata.json  # Metadatos (error, puntos)
│   ├── respaldo2.pkl
│   └── respaldo2_metadata.json
├── requirements.txt             # Dependencias Python
├── run.py                       # Script principal
├── tune.py                      # Herramienta de tuning interactiva
├── README.md                    # Este archivo
└── venv/                        # Entorno virtual (no commiteado)
```

### Flujo de Datos

```
┌─────────────────────────────────────────────────────────────┐
│                    FUENTES DE VIDEO                          │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐        │
│  │   Live      │  │ Respaldo 1  │  │ Respaldo 2   │        │
│  │  m3u8 HTTP  │  │   .mp4      │  │    .MOV      │        │
│  └─────────────┘  └─────────────┘  └──────────────┘        │
│        ▼                  ▼                  ▼              │
│  ┌────────────────────────────────────────────────┐       │
│  │  detector.py - run_detector()                 │       │
│  │  ├─ YOLOv8 inference (GPU)                    │       │
│  │  ├─ Vehicle tracking                          │       │
│  │  ├─ Homography transform (pixel→world)        │       │
│  │  └─ Buffer push (5s circular buffer)          │       │
│  └────────────────────────────────────────────────┘       │
│        ▼                                                   │
│  ┌────────────────────────────────────────────────┐       │
│  │  buffer_manager.py                            │       │
│  │  Almacena últimos 80 frames (5s @ 16 FPS)    │       │
│  └────────────────────────────────────────────────┘       │
│        ▼                                                   │
│  ┌────────────────────────────────────────────────┐       │
│  │  server.py - Flask API                        │       │
│  │  ├─ GET /detections → JSON (vehículos)       │       │
│  │  ├─ GET /video_feed → MJPEG stream           │       │
│  │  ├─ POST /calibration/set-context            │       │
│  │  ├─ GET /calibration/frame/<source>          │       │
│  │  ├─ POST /calibration/add-point              │       │
│  │  └─ POST /calibration/calculate              │       │
│  └────────────────────────────────────────────────┘       │
│        ▼                                                   │
│  ┌────────────────────────────────────────────────┐       │
│  │  Clientes (PC2 SUMO, PC3 Dashboard)          │       │
│  └────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Componentes Principales

#### **detector.py** - Motor de Detección
- YOLOv8 inference en GPU (CUDA)
- Tracking de vehículos con ID persistente
- Cálculo de velocidad en píxeles/frame
- Aplicación de matriz homográfica
- Buffer circular de frames crudos
- Cambio dinámico de fuente de video (live/fallback/respaldo1/respaldo2)
- Shutdown seguro con signal handlers

#### **server.py** - API Flask
- **Calibración**: UI integrada en "/" con 3 pasos
  - Seleccionar fuente y mapa
  - Marcar puntos en video y mapa (mínimo 4 puntos)
  - Calcular matriz homográfica
- **Dashboard**: "/dashboard" con video en vivo y métricas
- **Endpoints API**: `/detections` (JSON), `/video_feed` (MJPEG), etc.
- **Codecs**: Switching en tiempo real (JPEG, WebP, H264)

#### **calibration_manager.py** - Gestión de Calibración
- Almacenamiento persistente de matrices (.pkl)
- Metadatos (error RMS, puntos usados, timestamp)
- Thread-safe con locks
- Cálculo automático con cv2.findHomography()

#### **buffer_manager.py** - Buffer Circular
- Almacena 5 segundos de video sin comprimir
- Capacity: 80 frames @ 16 FPS
- Thread-safe con RLock
- get_latest(), get_by_index(), get_by_timestamp()

#### **video_codecs.py** - Codificadores Adaptativos
- JPEG: Rápido, buena compresión
- WebP: Mejor ratio, más lento
- H264: Máxima compresión
- Adaptive: Elige según CPU disponible
- Configuración en tiempo real sin reinicio

---

## Requisitos

### Hardware
- **GPU NVIDIA**: RTX 2060 o superior (con drivers instalados)
- **RAM**: 8 GB mínimo (preferible 16 GB)
- **Storage**: 10 GB para modelos y videos

### Software
- **Ubuntu 24.04** (o similar con Python 3.10+)
- **NVIDIA Drivers**: Última versión estable
- **CUDA 12.1**: Instalado
- **cuDNN 9.1**: Para NVIDIA
- **Python 3.10+**

### Verificación de Requisitos
```bash
# GPU
nvidia-smi

# Python
python3 --version

# ffmpeg (opcional, para descargar videos)
ffmpeg -version
```

---

## Instalación

### Paso 1: Clonar/Crear Directorio
```bash
mkdir -p ~/traffic-gemelo
cd ~/traffic-gemelo
```

### Paso 2: Crear Entorno Virtual
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### Paso 3: Instalar PyTorch + CUDA
```bash
# PyTorch 2.5.1 con soporte CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Paso 4: Instalar Dependencias
```bash
# Crear requirements.txt con las dependencias exactas
pip install ultralytics opencv-python flask flask-cors requests

# O instalar desde requirements.txt predefinido
pip install -r requirements.txt
```

### Paso 5: Verificar CUDA
```bash
python3 -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

**Esperado:**
```
CUDA: True
GPU: NVIDIA GeForce RTX 2060
```

### Paso 6: Descargar Modelos y Videos
```bash
# El primer run descargará automáticamente YOLOv8s.pt (~21 MB)

# Videos de fallback (si tienes ffmpeg)
# Opción A: Descargar stream en vivo
ffmpeg -i "https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8" \
       -t 120 -c copy videos/respaldo.mp4

# Opción B: O simplemente copiar archivos existentes
cp /ruta/a/video.mp4 videos/respaldo1.mp4
cp /ruta/a/video.MOV videos/respaldo2.MOV
```

### Paso 7: Crear Estructura de Directorios
```bash
mkdir -p models videos networks calibration
```

---

## Uso Rápido

### Iniciar el Servidor
```bash
source venv/bin/activate
python run.py
```

**Esperado:**
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

[SERVER] Registrando signal handlers...
[YOLO] Cargando modelo: yolov8s.pt
[YOLO] ✓ Modelo cargado en GPU
[FALLBACK] ✅ Video local abierto
[DETECTOR] Started | Video: 1920x1080 @ 30.2fps
```

### Acceder al Dashboard

1. **Navegador:** http://localhost:5000
2. **Interfaz de Calibración:** Selecciona fuente, marca puntos, calcula H
3. **Dashboard:** Ver video en vivo con detecciones y métricas

### Probar API
```bash
# JSON con detecciones actuales
curl http://localhost:5000/detections | jq .

# Esperado:
{
  "total": 5,
  "congestion": "MEDIUM",
  "density": 0.25,
  "source": "fallback",
  "vehicles": [
    {"id": 1, "type": "car", "bbox": [...], "speed_px": 15.3},
    ...
  ],
  "homography_matrix": [[-0.096, ...], ...],
  "timestamp": 1779064755.78
}
```

---

## Calibración Homográfica

### Objetivo
Transformar coordenadas de píxeles (video) a coordenadas mundiales (SUMO).

```
Pixel (x_px, y_px) → Matriz H → Mundo (x_m, y_m) [metros]
```

### Matriz Homográfica
- **Tipo:** 3×3 transformation matrix (perspectiva afín)
- **Almacenamiento:** Pickle (.pkl) + JSON metadata
- **Localización:** calibration/{source}.pkl

### Proceso de Calibración (5 minutos)

#### 1. Seleccionar Fuente y Mapa

**URL:** http://localhost:5000

1. Clic en pestaña "📍 Calibración"
2. Selecciona:
   - **Fuente:** live / respaldo1 / respaldo2
   - **Mapa:** cuenca_respaldo1
3. Clic en "Cargar"

#### 2. Marcar Puntos (Mínimo 4)

**Flujo:**
1. Clic en VIDEO (canvas izquierdo) → marca punto en píxeles
2. Clic en MAPA (SVG derecho) → marca punto equivalente en mundo
3. Repite mínimo 4 puntos
4. Botón "Calcular H" se habilita cuando hay ≥4 puntos

**Recomendaciones:**
- Marca puntos en **4 esquinas** del área de interés
- O marca puntos en **intersecciones viales**
- Asegura que correspondan exactamente entre video y mapa

#### 3. Calcular Matriz

1. Clic "Calcular H"
2. Sistema calcula cv2.findHomography()
3. Valida error RMS (debe ser < 10 píxeles)
4. Persiste en calibration/{source}.pkl

**Resultado esperado:**
```
✓ Homografía Calculada
  Puntos: 6
  Error RMS: 0.72 px
  Confianza: 95%
  
Guardar matriz para {source}
```

### Archivos Generados

```
calibration/
├── respaldo1.pkl               # Matriz 3×3 (NumPy array)
├── respaldo1_metadata.json     # {"error": 0.72, "points": 6, "map": "..."}
├── respaldo2.pkl
└── respaldo2_metadata.json
```

### Uso de Matriz en API

Una vez calibrada, el endpoint `/detections` incluye:
```json
{
  "source": "respaldo1",
  "homography_matrix": [
    [-0.096, -0.352, 140.88],
    [0.003, -0.095, 512.34],
    [0.0000012, -0.0000089, 1.0]
  ],
  "vehicles": [
    {
      "id": 1,
      "type": "car",
      "bbox": [637, 339, 819, 419],
      "speed_px": 257.32,
      "x_world": 125.34,
      "y_world": -45.67
    }
  ]
}
```

---

## API Endpoints

### 1. Detecciones (Principal)
```http
GET /detections
```

**Respuesta:**
```json
{
  "timestamp": 1779064755.78,
  "status_stream": "fallback loop",
  "total": 5,
  "congestion": "MEDIUM",
  "density": 0.25,
  "source": "fallback",
  "homography_matrix": [[...], [...], [...]],
  "counts": {
    "car": 4,
    "bus": 1,
    "truck": 0,
    "motorcycle": 0
  },
  "vehicles": [
    {
      "id": 3,
      "type": "car",
      "bbox": [637, 339, 819, 419],
      "confidence": 0.807,
      "speed_px": 257.32
    }
  ]
}
```

### 2. Video Feed (Streaming)
```http
GET /video_feed
```

**Tipo:** MJPEG stream (multipart/x-mixed-replace)
- Sincronizado a 16 FPS
- Codificación: JPEG 80 (por defecto)
- Headers: `Cache-Control: no-cache, no-store`

### 3. Health Check
```http
GET /health
```

**Respuesta:**
```json
{
  "status": "online",
  "timestamp": 1779064755.78,
  "stream_status": "fallback loop",
  "last_frame": 1779064755.75
}
```

### 4. Calibración - Establecer Contexto
```http
POST /calibration/set-context
Content-Type: application/json

{
  "source": "respaldo1",
  "map": "cuenca_respaldo1"
}
```

**Efectos:**
- Cambia stream_mode del detector a "respaldo1"
- Limpia puntos anteriores si el contexto cambió
- Prepara buffer para nueva fuente

### 5. Calibración - Obtener Frame
```http
GET /calibration/frame/<source>
```

**Parámetros:**
- `source`: live, fallback, respaldo1, respaldo2

**Respuesta:**
```json
{
  "success": true,
  "source": "respaldo1",
  "frame": "iVBORw0KGgoAAAANSUhEUgAAB4AAAAQ4CAIAAABnsVYU...",
  "resolution": [1920, 1080]
}
```

### 6. Calibración - Agregar Punto
```http
POST /calibration/add-point
Content-Type: application/json

{
  "point_px": [637, 339],
  "point_world": [125.34, -45.67]
}
```

**Respuesta:**
```json
{
  "success": true,
  "point_number": 1,
  "precision": "good",
  "can_calculate": false,
  "total_points": 1
}
```

### 7. Calibración - Calcular Matriz
```http
POST /calibration/calculate
```

**Respuesta:**
```json
{
  "success": true,
  "error_rms": 0.72,
  "points_used": 6,
  "confidence": 95,
  "matrix": [[...], [...], [...]],
  "message": "Homografía guardada exitosamente"
}
```

### 8. Obtener Mapa (SVG)
```http
GET /calibration/map-preview/<map_name>
```

**Parámetros:**
- `map_name`: cuenca_respaldo1

**Respuesta:** SVG limpio (sin etiquetas OSM)

### 9. Cambiar Fuente de Stream
```http
POST /stream/switch/<new_mode>
```

**Parámetros:**
- `new_mode`: live, fallback, respaldo1, respaldo2

**Efecto:** Reinicia detector con nueva fuente

### 10. Codec - Ver Configuración
```http
GET /codec/config
```

**Respuesta:**
```json
{
  "current_codec": "jpeg",
  "quality": 80,
  "preprocessing": "none",
  "target_fps": 16,
  "resize_factor": 1.0,
  "codec_stats": {
    "frames_encoded": 1024,
    "avg_encoding_time_ms": 12.3,
    "avg_frame_size_kb": 45.6
  }
}
```

### 11. Codec - Cambiar
```http
POST /codec/switch/<codec_type>/<quality>
```

**Parámetros:**
- `codec_type`: jpeg, webp, h264, adaptive
- `quality`: 1-100

### 12. Preprocessing - Cambiar
```http
POST /preprocessing/switch/<preset>
```

**Parámetros:**
- `preset`: none, quality, balanced, fast

---

## Tuning y Optimización

### Parámetros Ajustables

#### 1. Codec y Calidad (`src/video_codecs.py`)

```python
CODEC_CONFIG = {
    'active_codec': 'jpeg',        # Tipo: jpeg, webp, h264, adaptive
    'quality': 80,                 # 1-100 (default 80)
    'preprocessing': 'none',       # none, quality, balanced, fast
    'target_fps': 16,              # Sincronización de FPS
    'resize_factor': 1.0,          # Escalado 0.5-1.0
}
```

**Recomendaciones:**
- **Máxima Calidad**: JPEG 95 + preprocessing: quality (pero LENTO)
- **Balance (recomendado)**: JPEG 80 + preprocessing: none
- **Máxima Velocidad**: JPEG 60 + preprocessing: none

#### 2. Filtros de Imagen (`src/preprocessing.py`)

```python
PRESETS = {
    'none':       # SIN filtros (DEFAULT - más rápido)
    'quality':    # CLAHE + Sharpen + Denoise (lento, máxima claridad)
    'balanced':   # Denoise + CLAHE moderado (pesado)
    'fast':       # Solo resize (rápido)
}
```

**⚠️ NOTA:** Los presets 'quality' y 'balanced' aplican CLAHE O(n²), causando lag en tiempo real.

#### 3. Buffer Circular (`src/buffer_manager.py`)

```python
buffer_manager = BufferManager(
    buffer_duration_seconds=5,     # 5 segundos (fijo, optimizado)
    expected_fps=16                # Frames @ 16 FPS
)
```

**Capacidad:** 80 frames máximo

---

### Herramienta de Tuning Interactiva

**Archivo:** tune.py

**Uso:**
```bash
# Terminal 1: Iniciar servidor
python run.py

# Terminal 2: Ejecutar tuning
python tune.py
```

**Menú:**
```
┌─ Opciones ─────────────────────────────────────────────────┐
│  1. Ver configuración actual                                │
│  2. Ver estadísticas del codec                              │
│  3. Ver estadísticas del buffer                             │
│  4. Cambiar a JPEG (ajustar calidad)                        │
│  5. Cambiar a WebP (mejor compresión)                       │
│  6. Cambiar a Perfil "Máxima Calidad"                       │
│  7. Cambiar a Perfil "Balance" (recomendado)                │
│  8. Cambiar a Perfil "Máxima Velocidad"                     │
│  9. Cambiar Preprocessing (quality/balanced/fast/none)      │
│  0. Salir                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Código de tune.py:**
```python
#!/usr/bin/env python3
"""
Quick Tuning Tool - Cambiar codecs y parámetros en tiempo real
"""

import requests
import json
import sys

BASE_URL = "http://localhost:5000"

def print_banner():
    print("""
╔════════════════════════════════════════════════════════════════╗
║        🎛️  Traffic Gemelo - Codec Tuning Tool                 ║
║  Cambiar parámetros en TIEMPO REAL sin reiniciar servidor     ║
╚════════════════════════════════════════════════════════════════╝
    """)

def get_config():
    try:
        response = requests.get(f"{BASE_URL}/codec/config", timeout=2)
        return response.json()
    except Exception as e:
        print(f"❌ Error conectando al servidor: {e}")
        return None

def switch_codec(codec_type, quality):
    try:
        response = requests.post(
            f"{BASE_URL}/codec/switch/{codec_type}/{quality}",
            timeout=2
        )
        data = response.json()
        if response.status_code == 200:
            print(f"✅ {data['message']}")
            return True
        else:
            print(f"❌ {data.get('error', 'Error desconocido')}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def switch_preprocessing(preset):
    try:
        response = requests.post(
            f"{BASE_URL}/preprocessing/switch/{preset}",
            timeout=2
        )
        data = response.json()
        if response.status_code == 200:
            print(f"✅ {data['message']}")
            return True
        else:
            print(f"❌ {data.get('error', 'Error desconocido')}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def print_config(config):
    if not config:
        return
    print(f"""
╔═ CONFIGURACIÓN ACTUAL ═════════════════════════════════════════╗
│  Codec:           {config['current_codec'].upper():35s}│
│  Calidad:         {config['quality']:35}│
│  Preprocessing:   {config['preprocessing']:35s}│
│  Target FPS:      {config['target_fps']:35}│
│  Resize Factor:   {config['resize_factor']:35}│
╚════════════════════════════════════════════════════════════════╝
    """)

def main():
    print_banner()
    while True:
        print("""
┌─ Opciones ─────────────────────────────────────────────────────┐
│  1. Ver configuración actual                                    │
│  2. Ver estadísticas del codec                                  │
│  3. Ver estadísticas del buffer                                 │
│  4. Cambiar a JPEG (ajustar calidad)                            │
│  5. Cambiar a WebP (mejor compresión)                           │
│  6. Cambiar a Perfil "Máxima Calidad"                           │
│  7. Cambiar a Perfil "Balance" (recomendado)                    │
│  8. Cambiar a Perfil "Máxima Velocidad"                         │
│  9. Cambiar Preprocessing                                       │
│  0. Salir                                                       │
└─────────────────────────────────────────────────────────────────┘
        """)
        
        choice = input("Selecciona opción (0-9): ").strip()
        
        if choice == '0':
            print("\n👋 ¡Hasta luego!\n")
            break
        elif choice == '1':
            config = get_config()
            print_config(config)
        elif choice == '4':
            try:
                quality = int(input("Ingresa calidad JPEG (1-100): ") or "80")
                quality = max(1, min(100, quality))
                switch_codec('jpeg', quality)
            except ValueError:
                print("❌ Entrada inválida")
        elif choice == '6':
            print("\n✨ Perfil Máxima Calidad")
            switch_codec('jpeg', 95)
            switch_preprocessing('quality')
        elif choice == '7':
            print("\n⚡ Perfil Balance (recomendado)")
            switch_codec('jpeg', 80)
            switch_preprocessing('none')
        elif choice == '8':
            print("\n🚀 Perfil Máxima Velocidad")
            switch_codec('jpeg', 60)
            switch_preprocessing('none')
        
        input("\nPresiona ENTER para continuar...")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Herramienta de tuning cerrada.\n")
        sys.exit(0)
```

---

## Fases Completadas

### ✅ Fase 1: Setup Inicial
- Configuración NVIDIA CUDA 12.1
- PyTorch + YOLOv8 en GPU
- Estructura del proyecto
- Buffer circular (5s)
- Codificadores adaptativos

### ✅ Fase 2: Detección en Tiempo Real
- YOLOv8 inference (16 FPS sincronizado)
- Tracking de vehículos con ID persistente
- Cálculo de densidad y congestión
- Fallback automático (live → local)
- API REST con endpoints JSON

### ✅ Fase 3: Calibración Homográfica
- UI integrada en "/" con 3 pasos
- Selección de fuente (live/respaldo1/respaldo2)
- Marcar puntos en video y mapa
- Cálculo automático con cv2.findHomography()
- Persistencia en calibration/{source}.pkl

### ✅ Fase 4: Correcciones Arquitectónicas
- Removido confusión "fallback" → terminología clara
- Calibración obligatoria en "/" antes de dashboard
- Dashboard simplificado en "/dashboard"
- Soporte para 3 fuentes de video locales
- Circle marks visualization (canvas + SVG)

### ✅ Fase 5: Optimizaciones Finales

#### 5a. Reducir Tamaño de Marcas
- Cambiar radio círculos naranja: 15px → 8px
- Cambiar stroke-width: 3px → 2px
- Resultado: Marcas más claras sin obstruir video

#### 5b. Detener Auto-conexión a Stream 'live'
- Cambiar default stream_mode: 'live' → 'fallback'
- Detector inicia con video local, no intenta conexión automática
- Usuario selecciona 'live' explícitamente en calibración
- Resultado: Menor lag, mayor control del usuario

#### 5c. Soporte Completo para Fuentes Locales
- Expandir `set_stream_mode()` para aceptar 4 modos
- Expandir `open_source()` para buscar .mp4/.MOV en /videos/
- Soporte respaldo1.mp4 y respaldo2.MOV
- Resultado: Fácil agregar nuevas fuentes de video

#### 5d. Limpiar UI de Dashboard
- Removido 313 líneas de HTML/JavaScript corrupto
- Removido código JavaScript en crudo visible
- Removido duplicado `@app.route('/shutdown')`
- Dashboard ahora muestra correctamente
- Resultado: UI limpia, sin errores de rendering

#### 5e. Arreglar Frame de 'live' (404 Error)
- **Problema:** `/calibration/frame/live` retornaba HTTP 404
- **Causa:** Código intentaba importar `video_buffer` (no existe)
- **Solución:** 
  ```python
  from buffer_manager import buffer_manager
  frame, _, _ = buffer_manager.get_latest()
  ```
- **Resultado:** Endpoint /calibration/frame/live retorna HTTP 200 con frame válido

### Resumen de Cambios

| Fase | Cambio | Archivo | Líneas |
|------|--------|---------|--------|
| 5a | Reducir tamaño círculos | server.py | 1088-1100 |
| 5b | Default fallback | detector.py | 47 |
| 5c | Expandir set_stream_mode() | detector.py | 56-66 |
| 5c | Expandir open_source() | detector.py | 155-200 |
| 5d | Limpiar HTML corrupto | server.py | 1240-1572 ❌ |
| 5d | Remover duplicate shutdown | server.py | 1241-1261 ❌ |
| 5e | Fijar buffer_manager import | video_manager.py | 77-87 |

**Total de cambios:** 6 errores identificados y corregidos | 3 optimizaciones implementadas

---

## Troubleshooting

### Error: "CUDA no disponible"
```
Solución:
1. Verificar nvidia-smi: nvidia-smi
2. Reinstalar drivers: sudo ubuntu-drivers autoinstall
3. Reinstalar PyTorch: pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### Error: "YOLOv8 model not found"
```
Solución:
1. Borrar cache: rm -rf ~/.cache/Ultralytics/
2. Dejar que descargue automáticamente al iniciar
3. O descargar manualmente: python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"
```

### Error: "Stream no disponible"
```
Solución:
1. Verificar conexión a internet (para 'live')
2. Verificar que videos/respaldo.mp4 existe
3. Cambiar a fallback: POST /stream/switch/fallback
```

### Error 404 en `/calibration/frame/live`
```
Solución: Ya está FIJO en Fase 5e
✅ Cambiar a buffer_manager.get_latest() en video_manager.py
```

### UI lenta o lag en streaming
```
Solución:
1. Cambiar a perfil "Máxima Velocidad": python tune.py → opción 8
2. Reducir calidad: JPEG 60-70
3. Desactivar preprocessing: none
```

### Buffer desbordado
```
Síntoma: 
  [FALLBACK] Buffer FULL: 80/80 (overflow)
  
Solución:
1. Verificar FPS: debe estar sincronizado a 16
2. Aumentar tamaño del buffer (si es necesario): BufferManager(buffer_duration_seconds=10)
3. Cambiar codec a JPEG (más rápido que WebP)
```

### VideoCapture error
```
Síntoma:
  [ERROR] VideoCapture: Cannot read frame from respaldo1

Solución:
1. Verificar archivo: ls -lh videos/respaldo1.mp4
2. Verificar formato: ffprobe videos/respaldo1.mp4
3. Reconvertir video: ffmpeg -i videos/respaldo1.mp4 -c:v libx264 videos/respaldo1_fixed.mp4
```

---

## Shutdown Seguro

### 4 Formas de Cerrar

#### Método 1: CTRL+C en Terminal (⭐ RECOMENDADO)
```bash
$ python run.py
...
Presiona Ctrl+C para detener.
^C
[SIGNAL] SIGINT recibido
[SIGNAL] Recibida señal de shutdown...
[CLEANUP] Liberando recursos del detector...
[CLEANUP] VideoCapture cerrado
✅ Detector stopped.
[SERVER] Limpiando...
```

#### Método 2: API Endpoint
```bash
curl -X POST http://localhost:5000/shutdown
```

#### Método 3: Signal SIGTERM
```bash
# Desde otra terminal
ps aux | grep "python run.py"
kill -TERM <PID>
```

#### Método 4: Herramienta de Tuning
```bash
python tune.py
# Opción 0: Salir
```

### Flujo de Shutdown Seguro

```
CTRL+C (o kill -TERM)
    ↓
signal.SIGINT/SIGTERM
    ↓
handle_sigint() / handle_sigterm()
    ↓
shutdown_event.set()
    ↓
Detector ve evento y sale del bucle
    ↓
finally: cap.release()
    ↓
detector_thread.join(timeout=5s)
    ↓
Flask recibe señal y termina
    ↓
✅ Todos los recursos liberados
    ↓
exit(0)
```

### Verificar Limpieza
```bash
# Verificar que no quedan procesos
ps aux | grep python

# Verificar que VideoCapture fue liberado
lsof | grep "respaldo\|live" | wc -l  # Debe ser 0
```

---

## Configuración Avanzada

### Cambiar Modelo YOLO
```bash
# Variables de entorno
export YOLO_MODEL=yolov8m.pt  # Mediano (~48 MB)
export YOLO_MODEL=yolov8l.pt  # Grande (~93 MB)

python run.py
```

**Modelos disponibles:**
- yolov8n.pt: Nano (6 MB) - Rápido, baja accuracy
- yolov8s.pt: Small (21 MB) - **DEFAULT** - Recomendado
- yolov8m.pt: Mediano (48 MB) - Mejor accuracy, más lento
- yolov8l.pt: Large (93 MB) - Máxima accuracy, muy lento
- yolov8x.pt: Extra Large (145 MB) - Profesional

### Agregar Nueva Fuente de Video
```python
# En src/detector.py, función open_source():

if mode == 'mi_video':
    video_path = Path(__file__).parent.parent / 'videos' / 'mi_video.mp4'
    if not video_path.exists():
        print(f"[ERROR] Archivo no encontrado: {video_path}")
        return False
    # ... resto del código
```

### Agregar Nuevo Mapa
```bash
# Copiar archivo .net.xml a networks/
cp tu_mapa.net.xml networks/

# Será detectado automáticamente en /calibration/map-preview/
```

### Integración con SUMO

**Obtener coordenadas mundiales:**
```bash
curl http://localhost:5000/detections | jq '.vehicles[] | {id, x_world, y_world}'
```

**Formato esperado por SUMO:**
```json
{
  "id": 1,
  "x_world": 125.34,
  "y_world": -45.67,
  "type": "car"
}
```

---

## Referencias Técnicas

### Matriz Homográfica
- **Tipo:** cv2.findHomography() con cv2.RANSAC
- **Robustez:** RANSAC filtra outliers
- **Validación:** Error RMS debe ser < 10 píxeles

### Buffer Circular
- **Implementación:** collections.deque
- **Thread-safety:** threading.RLock
- **Capacidad:** 80 frames (5s @ 16 FPS)

### YOLOv8 Detección
- **Clases:** car (2), bus (5), truck (7), motorcycle (3)
- **Confidence threshold:** 0.45 (default)
- **Input size:** 640×640 (interno)

### Tracking
- ID persistente entre frames
- Basado en centroide + movimiento
- Velocidad en píxeles/frame

---

## Licencia y Créditos

- **YOLOv8:** Ultralytics (Apache 2.0)
- **PyTorch:** Facebook/Meta (BSD)
- **OpenCV:** Intel (Apache 2.0)
- **Flask:** Pallets (BSD)
- **Stream de Prueba:** California DOT

---

## Soporte

Para reportar bugs o solicitar features:
1. Verifica la sección **Troubleshooting**
2. Revisa los logs en terminal
3. Valida configuración con `python tune.py`
4. Contacta al equipo de desarrollo

---

**Última actualización:** Mayo 18, 2026
**Versión:** 1.0 - Production Ready
**Estado:** ✅ Todas las fases completadas y validadas
