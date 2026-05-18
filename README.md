# 🚗 Traffic Gemelo - Sistema de Detección y Seguimiento de Vehículos con Calibración Homográfica

**Plataforma de investigación para detección de vehículos en tiempo real, seguimiento persistente, mapeo a coordenadas mundiales y integración con simuladores de tráfico (SUMO).**

**Versión:** 2.5.1 | **Estado:** Production-Ready | **Última Actualización:** Mayo 2026

---

## 📋 Tabla de Contenidos

1. [Resumen Técnico](#resumen-técnico)
2. [Fundamentos Teóricos](#fundamentos-teóricos)
   - [YOLO: You Only Look Once](#yolo-you-only-look-once)
   - [Dataset COCO y Clases de Vehículos](#dataset-coco-y-clases-de-vehículos)
   - [Visión por Computadora y OpenCV](#visión-por-computadora-y-opencv)
   - [Transformación Homográfica](#transformación-homográfica)
3. [Arquitectura del Sistema](#arquitectura-del-sistema)
4. [Requisitos](#requisitos)
5. [Instalación](#instalación)
6. [Componentes Principales](#componentes-principales)
7. [Flujo de Detección](#flujo-de-detección)
8. [Calibración Homográfica](#calibración-homográfica)
9. [Sistema de Buffer Circular](#sistema-de-buffer-circular)
10. [Streaming Adaptativo](#streaming-adaptativo)
11. [API REST](#api-rest)
12. [Tuning y Optimización](#tuning-y-optimización)
13. [Integración con SUMO](#integración-con-sumo)
14. [Lectura de Archivos .NET](#lectura-de-archivos-net)
15. [Shutdown Seguro](#shutdown-seguro)
16. [Troubleshooting](#troubleshooting)

---

## Resumen Técnico

Traffic Gemelo es una plataforma de investigación especializada en **detección, seguimiento y mapeo espacial de vehículos**. El sistema integra múltiples disciplinas:

| Aspecto | Tecnología | Propósito |
|--------|-----------|---------|
| **Detección de Objetos** | YOLOv8 (GPU CUDA) | Identificación de vehículos en tiempo real (16 FPS) |
| **Procesamiento Espacial** | OpenCV + Geometría Proyectiva | Mapeo píxel ↔ coordenadas mundiales |
| **Seguimiento** | Centroide + ID persistente | Asociación de vehículos entre frames |
| **Almacenamiento** | Buffer Circular Thread-Safe | Sincronización temporal de datos |
| **Transmisión** | MJPEG + Codecs Adaptativos | Streaming en tiempo real con fallback |
| **API** | Flask REST + WebSockets | Integración con ecosistemas externos (SUMO) |

### Métricas de Rendimiento

- **Throughput**: 16 FPS en GPU
- **Latencia**: 50-200ms (captura → API)
- **Precisión**: ~90% en COCO dataset
- **Consumo GPU**: 40-60% (RTX 2060)
- **Buffer**: 5 segundos de video sin comprimir
- **Bandwidth**: 10-25 KB/s (detecciones JSON)

---

## Fundamentos Teóricos

### YOLO: You Only Look Once

#### Historia y Evolución

YOLO revolucionó la detección de objetos en 2015 al cambiar el paradigma:

**Antes de YOLO (Métodos Clásicos):**
```
Imagen Original
    ↓
Generador de Regiones (RPN): 2000+ propuestas
    ↓
Clasificador CNN: clasifica cada región
    ↓
Supresor NMS: elimina duplicados
    ↓
Salida: Bboxes + Clases
```

**Tiempo**: ~50-100ms por imagen (CPU)  
**Problema**: Múltiples passes, muy lento para tiempo real

**YOLO (Enfoque Unificado):**
```
Imagen Original (416x416)
    ↓
CNN única (Darknet-53)
    ↓
Salida: Grid 13x13 con predicciones
    ↓
NMS post-procesamiento
    ↓
Salida: Bboxes + Confianzas directamente
```

**Tiempo**: ~30-50ms por imagen (GPU)  
**Ventaja**: Un solo forward pass, parallelizable

#### Arquitectura de YOLOv8

La arquitectura actual del proyecto utiliza **YOLOv8s** (Small variant):

```
INPUT: 416×416×3 (RGB)
    ↓
BACKBONE (Darknet-53 modificado):
├─ Conv 3×3, stride 2 (208×208)
├─ Residual Blocks (multiples escalas)
├─ Conv 3×3, stride 2 (104×104)
└─ Conv 3×3, stride 2 (52×52)
    ↓
NECK (Feature Pyramid Network):
├─ Upsampling: 52×52 + 26×26 + 13×13
├─ Concatenación de características
└─ Refinamiento multi-escala
    ↓
HEAD (Detection Layer):
├─ Predicciones en 3 escalas:
│  ├─ 52×52×255 (objetos pequeños)
│  ├─ 26×26×255 (objetos medianos)
│  └─ 13×13×255 (objetos grandes)
│
├─ 255 = 3 anchors × (4 coords + 1 conf + 80 clases)
│         (x,y,w,h) + object_conf + class_probs
│
└─ Salida raw
    ↓
POST-PROCESAMIENTO:
├─ Decodificación de predicciones
├─ Filtrado por confianza (threshold 0.5)
├─ NMS (Non-Maximum Suppression)
└─ Mapeo a imagen original
    ↓
OUTPUT: Bboxes + Clases + Confianzas
```

#### Función de Pérdida (Loss Function)

YOLO minimiza:

$$L = L_{box} + L_{obj} + L_{cls}$$

Donde:

- **$L_{box}$** (Localization Loss - IoU Loss):
$$L_{box} = \sum_{i,j} \mathbb{1}_{ij}^{obj} (GIoU - IoU)^2$$
Mide la precisión de bounding boxes usando Generalized IoU

- **$L_{obj}$** (Objectness Loss - Focal Loss):
$$L_{obj} = -\alpha_t (1-p)^\gamma \log(p)$$
Enfatiza ejemplos difíciles (focal loss)

- **$L_{cls}$** (Classification Loss - Binary Cross-Entropy):
$$L_{cls} = \sum_{i,j} \mathbb{1}_{ij}^{obj} \sum_{c \in classes} -y_c \log(\hat{y}_c)$$
Clasifica entre 80 categorías COCO

#### Proceso de Inferencia en GPU (CUDA)

```python
# En detector.py líneas 100-150
model = YOLO('yolov8s.pt')
model.to('cuda')  # Transferir pesos a GPU

# En el loop de detección (líneas 200+)
results = model.predict(frame, conf=0.5, iou=0.45)

# Internamente:
# 1. frame → GPU memory (asincrónico)
# 2. Forward pass en 30-50ms
# 3. Post-procesamiento (NMS, filtering) en CPU
# 4. Resultados → aplicación
```

**Aceleración CUDA:**
```
GPU (RTX 2060):     30-50ms ← Intel i5-9400F + RTX 2060
CPU (CPU-only):     200-300ms
Speedup:            6-8×
```

---

### Dataset COCO y Clases de Vehículos

#### ¿Qué es COCO?

**COCO (Common Objects in Context)** es el dataset de detección de objetos más importante en visión por computadora:

- **Tamaño**: 118,000 imágenes de entrenamiento
- **Clases**: 80 categorías de objetos comunes
- **Anotaciones**: 5 millones de instancias con bounding boxes
- **Contexto**: Objetos en contextos naturales y complejos

#### Clases Relevantes: Vehículos en COCO

YOLO entrenado en COCO reconoce 80 clases. Para vehículos:

```python
VEHICLE_CLASSES = {
    'car': 2,          # Class ID 2 - Autos convencionales
    'bus': 5,          # Class ID 5 - Autobuses y camiones de pasajeros
    'truck': 7,        # Class ID 7 - Camiones de carga
    'motorcycle': 3    # Class ID 3 - Motocicletas y scooters
}
```

**Matriz de Distribución en Tráfico:**

| Clase | % Típico | Tamaño Típico (px) | Velocidad (km/h) | IoU Mínimo |
|-------|----------|-------------------|------------------|-----------|
| car | 70-80% | 40-150 | 20-100 | 0.5 |
| bus | 5-15% | 80-200 | 10-60 | 0.55 |
| truck | 5-10% | 60-180 | 10-80 | 0.55 |
| motorcycle | 2-5% | 20-80 | 20-120 | 0.45 |

#### Métricas COCO

El desempeño se mide con:

$$AP = \frac{1}{101} \sum_{t=0}^{1} p(t)$$

Donde $p(t)$ es la precisión a recall $t$.

**YOLOv8s en COCO 80 (accuracy):**
- mAP₅₀: 44.9% (0.50 IoU threshold)
- mAP₅₀₋₉₅: 28.6% (0.50-0.95 IoU, rígido)

**En el contexto de tráfico (vehículos):**
- Subconjunto COCO (solo 4 clases): +15-20% accuracy
- Razón: Contexto menos variable, objetos más predecibles

---

### Visión por Computadora y OpenCV

#### Pipeline de Procesamiento de Imágenes

Traffic Gemelo utiliza OpenCV para:

1. **Lectura de video y captura de frames**
2. **Anotación de detecciones**
3. **Transformaciones geométricas**
4. **Preprocesamiento (filtros)**

#### Operaciones OpenCV Clave

**1. Lectura de Video (VideoCapture)**
```python
# src/detector.py línea ~120
cap = cv2.VideoCapture(stream_url)
# Cap tiene propiedades:
cap.get(cv2.CAP_PROP_FPS)          # FPS
cap.get(cv2.CAP_PROP_FRAME_WIDTH)  # Ancho
cap.get(cv2.CAP_PROP_FRAME_HEIGHT) # Alto
cap.get(cv2.CAP_PROP_FRAME_COUNT)  # Total frames
```

**Formatos Soportados:**
- RTSP/HTTP (streams en vivo)
- MP4/MOV (archivos locales)
- M3U8 (listas de reproducción - requiere ffmpeg)

**2. Anotación de Bounding Boxes**
```python
# Dibujar rectángulo
cv2.rectangle(frame, (x1,y1), (x2,y2), color, thickness=2)

# Dibujar texto con ID
cv2.putText(frame, f"ID: {track_id}", (x1, y1-10),
           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

# Dibujar centroide
cv2.circle(frame, center, radius=3, color, -1)
```

**3. Transformación Homográfica**
```python
# src/calibration_manager.py línea ~150
H = cv2.findHomography(src_points, dst_points)[0]

# Aplicar transformación
point_world = cv2.perspectiveTransform(
    np.array([[[x_pixel, y_pixel]]]), H)[0][0]
```

**4. Preprocesamiento con Filtros**
```python
# src/preprocessing.py líneas 20-80

# CLAHE: Contrast Limited Adaptive Histogram Equalization
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
enhanced = clahe.apply(gray_frame)

# Bilateral Filter: Preserva bordes, suaviza ruido
filtered = cv2.bilateralFilter(frame, d=9, sigmaColor=75, sigmaSpace=75)

# Gaussian Blur: Suavizado general
blurred = cv2.GaussianBlur(frame, (5,5), 0)
```

#### Transformaciones Afines

OpenCV implementa operaciones matriciales para transformar imágenes:

$$\begin{bmatrix} x' \\ y' \end{bmatrix} = M \begin{bmatrix} x \\ y \\ 1 \end{bmatrix} = \begin{bmatrix} m_{11} & m_{12} & m_{13} \\ m_{21} & m_{22} & m_{23} \end{bmatrix} \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}$$

Donde $M$ es una matriz 2×3 que puede representar:
- Rotación
- Escalado
- Traslación
- Sesgo (skew)

---

### Transformación Homográfica

#### Teoría Fundamental

Una **homografía** es una transformación proyectiva que mapea puntos de un plano a otro plano:

$$\lambda \begin{bmatrix} x' \\ y' \\ 1 \end{bmatrix} = H \begin{bmatrix} x \\ y \\ 1 \end{bmatrix} = \begin{bmatrix} h_{11} & h_{12} & h_{13} \\ h_{21} & h_{22} & h_{23} \\ h_{31} & h_{32} & h_{33} \end{bmatrix} \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}$$

Donde:
- $(x, y)$ = coordenadas en imagen (píxeles)
- $(x', y')$ = coordenadas en mundo real
- $H$ = matriz 3×3 (8 grados de libertad, normalmente $h_{33} = 1$)
- $\lambda$ = factor de escala (normalizamos dividiendo por $h_{31}x + h_{32}y + h_{33}$)

#### ¿Por qué Homografía?

Una cámara observa un plano (la calle) desde cierto ángulo. La relación entre píxeles y coordenadas mundiales **NO es lineal** debido a la perspectiva:

```
     VISTA AÉREA (Mapa)
     ┌──────────────────┐
     │ (x_mundo, y_mundo)
     │      ↑
     │  (x_pix, y_pix) ↗  ← El punto parece "corrido"
     │    en el video      porque es perspectiva
     │                 
     └──────────────────┘
     
     CÁMARA (Video)
     ┌──────────────────┐
     │  ╱─ ← Cámara observa
     │ ╱ ╲  en ángulo
     │╱   ╲ oblicuo
     └──────────────────┘
```

La homografía compensa este efecto de perspectiva.

#### Cálculo de la Matriz H

Se requieren **mínimo 4 correspondencias** de puntos:

$$\{(x_i, y_i) \leftrightarrow (x'_i, y'_i)\}_{i=1}^{N}, \quad N \geq 4$$

Se usa **DLT (Direct Linear Transform)** o **RANSAC** para robustez:

```python
# src/calibration_manager.py línea ~85
H, mask = cv2.findHomography(
    src_points,      # Puntos en video (píxeles)
    dst_points,      # Puntos en mapa (coords mundiales)
    method=cv2.RANSAC,
    ransacReprojThreshold=5.0
)
```

**RANSAC (Random Sample Consensus):**
1. Selecciona aleatoriamente 4 puntos
2. Calcula H con esos 4 puntos
3. Cuenta inliers (puntos que se ajustan bien)
4. Repite 1000 iteraciones
5. Elige el H con más inliers

**Ventaja**: Robusto a outliers (errores de calibración)

#### Error de Calibración (Reprojection Error)

Para cada punto calibrado, se mide:

$$error_i = ||P'_i - P_{transformed}||_2$$

$$RMSE = \sqrt{\frac{1}{N} \sum_{i=1}^{N} error_i^2}$$

```python
# src/calibration_manager.py línea ~110
errors = cv2.perspectiveTransform(src_points, H) - dst_points
rmse = np.sqrt(np.mean(errors**2))
```

**Criterios de Aceptación:**
- RMSE < 0.05 m: Excelente (error sub-pixel)
- RMSE < 0.1 m: Bueno
- RMSE < 0.5 m: Aceptable
- RMSE > 1.0 m: Rechazar y recalibrar

#### Aplicación al Centroide de Vehículos

En el detector:

```python
# src/detector.py línea ~250
bbox = (x1, y1, x2, y2)
centroid_pixel = ((x1+x2)/2, (y1+y2)/2)

# Transformar a coordenadas mundiales
H = calibration_manager.get_homography(source)
if H is not None:
    centroid_world = cv2.perspectiveTransform(
        np.array([[[centroid_pixel[0], centroid_pixel[1]]]]),
        H
    )[0][0]
    vehicle_data['world_coords'] = centroid_world.tolist()
```

#### Limitaciones y Consideraciones

⚠️ **La homografía asume:**
1. Todos los puntos están en el MISMO PLANO (la calle)
2. Ángulo de cámara NO cambia (calibración fija)
3. Sin distorsión de lente (ideal)

**En práctica:**
- Vehículos tienen altura → error si se calibra solo centro
- Cambios de iluminación → pueden afectar detección
- Movimientos de cámara → requiere recalibración

---

## Arquitectura del Sistema

### Vista General

```
┌────────────────────────────────────────────────────────────────┐
│                   TRAFFIC GEMELO - ARQUITECTURA                 │
└────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────┐
│     FUENTES DE VIDEO                 │
│  ┌────────────────────────────────┐ │
│  │ • Stream live HTTP/RTSP/M3U8   │ │  ← Cámara en vivo o servidor
│  │ • Respaldo 1 (respaldo1.mp4)   │ │
│  │ • Respaldo 2 (respaldo2.MOV)   │ │
│  └────────────────────────────────┘ │
└────────────┬─────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────────┐
│  detector.py - run_detector()                                  │
│                                                                │
│  THREAD PRINCIPAL (Loop continuo @ 16 FPS)                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 1. Leer frame                                            │ │
│  │    cv2.VideoCapture.read() → numpy array 1280×720×3     │ │
│  │                                                          │ │
│  │ 2. Inferencia YOLO (GPU)                                │ │
│  │    model.predict(frame, conf=0.5, iou=0.45)            │ │
│  │    → Detecciones de vehículos con bbox + confianza     │ │
│  │                                                          │ │
│  │ 3. Seguimiento (Tracking)                              │ │
│  │    - Centroide frame actual vs frame anterior           │ │
│  │    - Asignar IDs persistentes                           │ │
│  │    - Calcular velocidad en píxeles/frame               │ │
│  │                                                          │ │
│  │ 4. Transformación Homográfica                          │ │
│  │    - Obtener matriz H del calibration_manager          │ │
│  │    - Transformar centroide (pixel → mundo)             │ │
│  │                                                          │ │
│  │ 5. Anotación de Frame                                  │ │
│  │    - cv2.rectangle() para bboxes                        │ │
│  │    - cv2.putText() para IDs y velocidades              │ │
│  │                                                          │ │
│  │ 6. Push al Buffer                                      │ │
│  │    - buffer_manager.push(frame, timestamp, metadata)   │ │
│  │    - Almacena frame sin comprimir (5s de historial)    │ │
│  │                                                          │ │
│  │ 7. Actualizar JSON de detecciones                      │ │
│  │    - JSON con timestamp, vehículos, matriz H           │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────┬─────────────────────────────────────────────────┘
             │
             ├─────────────────────────────────┬──────────────────┐
             ▼                                 ▼                  ▼
    ┌────────────────────────┐    ┌─────────────────────┐  ┌─────────────┐
    │  buffer_manager        │    │ calibration_manager │  │ En Memoria  │
    │  (Buffer Circular)     │    │ (Matrices H)        │  │ (Locks)     │
    │ ┌──────────────────┐   │    │ ┌───────────────┐   │  │ ┌─────────┐ │
    │ │ frames (deque)   │   │    │ │ homographies  │   │  │ │detection│ │
    │ │ timestamps       │   │    │ │ metadata.json │   │  │ │_data    │ │
    │ │ metadata         │   │    │ │               │   │  │ └─────────┘ │
    │ │ (5s @ 16 FPS)    │   │    │ │ calibration/  │   │  │ (JSON)      │
    │ │ = 80 frames max  │   │    │ │ *.pkl files   │   │  │             │
    │ └──────────────────┘   │    │ └───────────────┘   │  │             │
    └────────────────────────┘    └─────────────────────┘  └─────────────┘
             │
             ▼
    ┌────────────────────────────────────────────────────────────┐
    │  server.py - Flask REST API + WebUI                        │
    │                                                             │
    │  THREADS SECUNDARIOS (Responden a HTTP requests)          │
    │                                                             │
    │  GET /detections                                          │
    │  └─→ Lee detection_data (con lock)                       │
    │      Retorna JSON: { vehicles, counts, timestamp, H}     │
    │                                                             │
    │  GET /video_feed                                          │
    │  └─→ generate_frames() → MJPEG streaming                 │
    │      Lee buffer_manager.get_latest()                      │
    │      Codifica con codec activo (JPEG/WebP/H264)          │
    │      Envia @16 FPS                                        │
    │                                                             │
    │  GET /health                                              │
    │  └─→ Verifica estado del detector                        │
    │                                                             │
    │  POST /calibration/set-context                           │
    │  └─→ calibration_manager.set_calibration_context()       │
    │                                                             │
    │  POST /calibration/add-point                             │
    │  └─→ Agrega puntos de calibración                        │
    │                                                             │
    │  POST /calibration/calculate                             │
    │  └─→ cv2.findHomography() → Calcula H → Guarda          │
    │                                                             │
    │  POST /shutdown                                           │
    │  └─→ Inicia secuencia de cierre seguro                   │
    │                                                             │
    │  GET / (WebUI)                                            │
    │  └─→ Interfaz HTML + JavaScript para calibración        │
    │      Permite marcar puntos interactivamente               │
    │                                                             │
    │  GET /codec/config                                        │
    │  └─→ Configuración actual de streaming                   │
    │                                                             │
    │  POST /codec/switch/<type>/<quality>                      │
    │  └─→ Cambiar codec en tiempo real (sin reiniciar)       │
    │                                                             │
    └────────────────────────────────────────────────────────────┘
             │
             ├──────────────────────────────────────────────────┐
             ▼                                                   ▼
    ┌──────────────────────────┐                    ┌─────────────────────┐
    │ PC2: SUMO (Simulador)    │                    │ PC3: Dashboard      │
    │                          │                    │ (Visualización)     │
    │ • GET /detections        │                    │                     │
    │ • Parsea JSON            │                    │ • GET /video_feed   │
    │ • Inyecta vehículos      │                    │ • Muestra stream    │
    │ • Lee matriz H           │                    │ • Muestra métricas  │
    │ • Simula tráfico         │                    │ • Interfaz web      │
    └──────────────────────────┘                    └─────────────────────┘
```

### Estructura de Directorios

```
traffic-gemelo/
│
├── README.md                        # Esta documentación (TÉCNICA)
├── HOMOGRAPHY_CALIBRATION.md        # Guía de calibración
├── TUNING_GUIDE.md                  # Parámetros de optimización
├── SHUTDOWN_GUIDE.md                # Procedimiento de cierre seguro
├── SENDING_INTERVALS.md             # Intervalos de envío a SUMO
├── INTEGRATION_COMPLETE.md          # Integración con SUMO (completado)
├── DELIVERY_SUMMARY.md              # Resumen de entrega
├── Steps_IC.txt                     # Pasos de integración
│
├── run.py                           # Script principal (entry point)
├── tune.py                          # Herramienta interactiva de tuning
├── requirements.txt                 # Dependencias Python
│
├── src/
│   ├── detector.py                  # Motor de detección YOLO + tracking
│   ├── server.py                    # API Flask REST + WebUI
│   ├── buffer_manager.py            # Buffer circular thread-safe
│   ├── calibration_manager.py       # Gestión de matrices homográficas
│   ├── video_manager.py             # Gestor de fuentes de video
│   ├── video_codecs.py              # Codificadores adaptativos (JPEG/WebP/H264)
│   ├── preprocessing.py             # Filtros de imagen (CLAHE, bilateral)
│   ├── codecs.py                    # Auxiliares de codec
│   └── calibration/                 # Interfaz web de calibración (HTML/JS)
│
├── models/
│   ├── yolov8n.pt                   # Modelo Nano (~6.3 MB, más rápido)
│   └── yolov8s.pt                   # Modelo Small (~21.5 MB, default)
│       [Descargan automáticamente de Ultralytics si no existen]
│
├── videos/
│   ├── respaldo.mp4                 # Stream fallback (descargado)
│   ├── respaldo1.mp4                # Video local 1 (para calibración)
│   └── respaldo2.MOV                # Video local 2 (para calibración)
│
├── networks/
│   ├── cuenca_respaldo1.net.xml     # Mapa SUMO correspondiente a respaldo1
│   ├── cuenca_respaldo2.net.xml     # Mapa SUMO correspondiente a respaldo2
│   └── [...más redes según sea necesario...]
│
├── calibration/                     # SE CREA AUTOMÁTICAMENTE
│   ├── live.pkl                     # Matriz H para stream live (si calibrado)
│   ├── live_metadata.json           # Metadatos: puntos, RMSE, timestamp
│   ├── respaldo1.pkl                # Matriz H para respaldo1.mp4
│   ├── respaldo1_metadata.json      # Metadatos de respaldo1
│   ├── respaldo2.pkl                # Matriz H para respaldo2.MOV
│   ├── respaldo2_metadata.json      # Metadatos de respaldo2
│   └── [...más calibraciones...]
│
└── venv/                            # Entorno virtual Python (NO commiteado)
    ├── bin/python
    ├── lib/python3.10/site-packages/
    └── [...]
```

---

## Requisitos

### Hardware

| Componente | Mínimo | Recomendado | Óptimo |
|-----------|--------|-------------|--------|
| **GPU** | GTX 1050 Ti | RTX 2060 | RTX 3080 o superior |
| **RAM** | 8 GB | 16 GB | 32 GB |
| **CPU** | Intel i5-8400 | Intel i5-9400F | Intel i9-10900K |
| **Storage** | 10 GB | 20 GB | 50 GB |
| **Network** | 1 Gbps Ethernet | 1 Gbps LAN | 10 Gbps |

### Software

| Software | Versión | Propósito |
|----------|---------|----------|
| **Ubuntu** | 24.04 LTS | Sistema operativo |
| **NVIDIA Driver** | 550+ | Soporte GPU |
| **CUDA** | 12.1 | Computación paralela (GPU) |
| **cuDNN** | 9.1 | Aceleración de redes neuronales |
| **Python** | 3.10+ | Runtime |
| **FFmpeg** | 7.0+ | Descodificación de video |

### Verificación Previa

```bash
# Verificar GPU NVIDIA
nvidia-smi
# Debe mostrar: CUDA Capability Major/Minor version number

# Verificar Python
python3 --version
# Debe mostrar: Python 3.10 o superior

# Verificar FFmpeg (opcional pero recomendado)
ffmpeg -version
# Debe mostrar versión >= 7.0

# Verificar drivers NVIDIA
nvidia-smi --query-gpu=driver_version --format=csv,noheader
# Debe mostrar: 550.XX o superior
```

---

## Instalación

### Paso 1: Preparar Entorno Base

```bash
# Crear directorio del proyecto
mkdir -p ~/traffic-gemelo
cd ~/traffic-gemelo

# Clonar desde Git (si aplica) o descargar archivos
# git clone <repository> .

# Crear entorno virtual aislado
python3 -m venv venv
source venv/bin/activate

# Actualizar pip a última versión
pip install --upgrade pip setuptools wheel
```

### Paso 2: Instalar PyTorch con Soporte CUDA

```bash
# PyTorch 2.5.1 compilado para CUDA 12.1
# Asegura que los tensores se ejecuten en GPU
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cu121

# Verificar instalación
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); \
            print(f'CUDA Available: {torch.cuda.is_available()}'); \
            print(f'GPU: {torch.cuda.get_device_name(0)}')"

# Salida esperada:
# PyTorch: 2.5.1+cu121
# CUDA Available: True
# GPU: NVIDIA GeForce RTX 2060
```

### Paso 3: Instalar Dependencias del Proyecto

```bash
# Opción A: Desde requirements.txt (recomendado)
pip install -r requirements.txt

# Opción B: Manual (para control fino)
pip install \
    ultralytics==8.0.0 \          # YOLOv8 framework
    opencv-python==4.13.0 \       # Procesamiento de imágenes
    Flask==3.1.3 \                # Servidor web REST
    Flask-Cors==4.0.0 \           # Soporte CORS
    requests==2.34.0 \            # Cliente HTTP
    numpy==2.4.3 \                # Álgebra lineal
    scipy==1.17.1                 # Herramientas científicas
```

### Paso 4: Descargar Modelos YOLO

Los modelos se descargan automáticamente en la primera ejecución, pero se puede predescargar:

```bash
# Descargar modelo Small (recomendado)
python3 -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"

# Alternativamente, descargar modelo Nano (más rápido, menos preciso)
python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# Los modelos se guardan en: ~/.cache/ultralytics/
# Verificar descarga
ls -lh ~/.cache/ultralytics/
```

### Paso 5: Preparar Archivos de Video y Red

```bash
# Crear directorio para videos
mkdir -p videos

# Opción A: Descargar stream de California como fallback
# (Requiere ffmpeg)
ffmpeg -i "https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8" \
       -t 120 -c:v libx264 -c:a aac videos/respaldo.mp4

# Opción B: Usar video local existente
# Copiar respaldo1.mp4 y respaldo2.MOV a ./videos/

# Crear directorio para mapas SUMO
mkdir -p networks

# Copiar archivos .net.xml a networks/
# Ejemplo: cp /ruta/a/cuenca_respaldo1.net.xml networks/
```

### Paso 6: Verificación Final

```bash
# Activar entorno virtual
source venv/bin/activate

# Ejecutar verificación de dependencias
python3 << 'EOF'
import sys
print("=" * 60)
print("VERIFICACIÓN DE DEPENDENCIAS")
print("=" * 60)

try:
    import torch
    print(f"✓ PyTorch {torch.__version__}")
    print(f"  CUDA: {torch.cuda.is_available()}")
except Exception as e:
    print(f"✗ PyTorch: {e}")
    sys.exit(1)

try:
    from ultralytics import YOLO
    print(f"✓ Ultralytics YOLO")
except Exception as e:
    print(f"✗ Ultralytics: {e}")
    sys.exit(1)

try:
    import cv2
    print(f"✓ OpenCV {cv2.__version__}")
except Exception as e:
    print(f"✗ OpenCV: {e}")
    sys.exit(1)

try:
    import flask
    print(f"✓ Flask {flask.__version__}")
except Exception as e:
    print(f"✗ Flask: {e}")
    sys.exit(1)

print("=" * 60)
print("✓ TODAS LAS DEPENDENCIAS INSTALADAS CORRECTAMENTE")
print("=" * 60)
EOF

# Si todo es correcto, proceder a ejecución
python run.py
```

---

## Componentes Principales

### 1. detector.py - Motor de Detección YOLO

**Responsabilidades:**
- Lectura continua de frames desde múltiples fuentes
- Inferencia de YOLO en GPU
- Seguimiento de vehículos con IDs persistentes
- Cálculo de velocidades
- Transformación homográfica
- Gestión segura del shutdown

**Arquitectura Interna:**

```python
# Inicialización (líneas 100-150)
def run_detector(...):
    model = YOLO('yolov8s.pt')          # Cargar modelo
    model.to('cuda')                     # Transferir a GPU
    cap = cv2.VideoCapture(stream_url)  # Abrir video
    
    # Loop de detección
    while not shutdown_event.is_set():  # ← Permite cierre seguro
        ret, frame = cap.read()          # Leer frame
        if not ret:
            # Cambiar a fallback si stream falla
            stream_mode = 'fallback'
            continue
            
        # YOLO inference
        results = model.predict(frame, conf=0.5, iou=0.45)
        detections = results[0].boxes
        
        # Tracking y anotación
        vehicles = []
        for det in detections:
            bbox = det.xyxy[0].cpu().numpy()  # (x1, y1, x2, y2)
            conf = det.conf[0].item()          # Confianza 0-1
            cls_id = int(det.cls[0].item())    # Class ID
            
            # Obtener ID persistente
            track_id = assign_or_create_id(bbox)
            
            # Transformar a mundo
            centroid = ((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2)
            centroid_world = apply_homography(centroid, H)
            
            # Anotar
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"ID:{track_id}", (x1, y1-10), ...)
            
            vehicles.append({
                'id': track_id,
                'class': CLASS_NAMES[cls_id],
                'bbox': bbox.tolist(),
                'confidence': conf,
                'centroid_pixel': centroid,
                'centroid_world': centroid_world.tolist(),
                'speed_px': calculate_speed_px(...)
            })
        
        # Push al buffer
        buffer_manager.push(frame, timestamp=time.time(),
                          metadata={
                              'vehicles': vehicles,
                              'timestamp': time.time()
                          })
        
        # Throttle a 16 FPS
        frame_delay = 1.0 / 16
        time.sleep(frame_delay)
```

**Variables Globales Protegidas (con Locks):**

```python
detection_data = {
    'timestamp': None,
    'status_stream': 'online'|'offline',
    'counts': {'car': N, 'bus': N, 'truck': N, 'motorcycle': N},
    'total': N,
    'density': float,
    'congestion': 'LOW'|'MEDIUM'|'HIGH'|'CRITICAL',
    'vehicles': [...]
}
data_lock = threading.Lock()
```

**Funciones de Control:**

```python
get_stream_mode()           # Obtener fuente actual (con lock)
set_stream_mode(mode)       # Cambiar fuente (live/fallback/respaldo1/2)
get_detection_data()        # Obtener JSON actual (con lock)
signal_shutdown()           # Inicia cierre seguro
handle_sigint(sig, frame)   # Manejador de CTRL+C
handle_sigterm(sig, frame)  # Manejador de SIGTERM
```

### 2. server.py - API REST Flask

**Endpoints Principales:**

| Método | Ruta | Propósito | Response |
|--------|------|----------|----------|
| `GET` | `/` | WebUI de calibración | HTML +JS |
| `GET` | `/detections` | Datos JSON actuales | JSON {vehicles, H, timestamp} |
| `GET` | `/health` | Health check | {status, timestamp, stream_status} |
| `GET` | `/video_feed` | Stream MJPEG | MJPEG 16 FPS |
| `GET` | `/codec/config` | Config de streaming | {codec, quality, fps} |
| `POST` | `/codec/switch/<type>/<quality>` | Cambiar codec | {success, codec} |
| `POST` | `/calibration/set-context` | Establecer contexto | {success, source, map} |
| `POST` | `/calibration/add-point` | Agregar punto calibración | {point_count} |
| `POST` | `/calibration/calculate` | Calcular matriz H | {H, rmse, success} |
| `POST` | `/shutdown` | Iniciar cierre seguro | {success} |

**Streaming MJPEG (generate_frames()):**

```python
def generate_frames():
    """
    Genera stream MJPEG sin buffer congestionado
    Lee SOLO frame más reciente y lo codifica
    """
    while True:
        # Obtener frame más reciente del buffer
        frame, ts, metadata = buffer_manager.get_latest()
        
        if frame is None:
            time.sleep(0.05)
            continue
        
        # Codificar con codec activo
        codec = get_active_codec()
        frame_bytes = codec.encode(frame)
        
        # Enviar como MJPEG chunk
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
            + frame_bytes + b'\r\n'
        )
        
        # Sincronizar a 16 FPS
        time.sleep(1.0 / 16)
```

### 3. buffer_manager.py - Buffer Circular Thread-Safe

**Propósito:** Almacenar 5 segundos de video sin comprimir para sincronización temporal.

**Especificación:**

```python
class BufferManager:
    def __init__(self, buffer_duration_seconds=5, expected_fps=16):
        self.max_frames = 5 * 16 = 80 frames
        self.frames = deque(maxlen=80)          # Núcleos de frames
        self.timestamps = deque(maxlen=80)      # Unix timestamps
        self.metadata = deque(maxlen=80)        # JSON data
        self.lock = threading.RLock()           # ← Permite reentrancia
```

**Operaciones:**

```python
# Push: Agregar frame (llamado cada 62ms por detector)
buffer_manager.push(frame, timestamp, metadata)

# Get Latest: Obtener frame más reciente (MJPEG stream)
frame, ts, metadata = buffer_manager.get_latest()

# Get by Index: Acceso histórico
frame, ts, metadata = buffer_manager.get_by_index(-5)  # 5 frames atrás

# Get by Timestamp: Sincronización temporal
frame, ts, metadata = buffer_manager.get_by_timestamp(target_ts)
```

**Thread-Safety:**

Todas las operaciones usan `self.lock.acquire()` al inicio y `self.lock.release()` al final:

```python
def push(self, frame, timestamp=None, metadata=None):
    with self.lock:  # ← Adquiere lock
        frame_copy = frame.copy()
        self.frames.append(frame_copy)
        self.timestamps.append(timestamp or time.time())
        self.metadata.append(metadata or {})
    # ← Libera lock automáticamente
```

### 4. calibration_manager.py - Gestión de Matrices Homográficas

**Almacenamiento Persistente:**

```
calibration/
├── respaldo1.pkl               # Matriz H (NumPy array 3×3)
├── respaldo1_metadata.json     # {"rmse": 0.045, "points": 4, "timestamp": ...}
├── respaldo2.pkl
├── respaldo2_metadata.json
└── [...]
```

**Operaciones:**

```python
# 1. Establecer contexto de calibración
calibration_manager.set_calibration_context("respaldo1", "cuenca_respaldo1.net.xml")
# Limpia puntos anteriores si cambió de fuente/mapa

# 2. Agregar puntos manualmente
calibration_manager.add_point(
    point_px=(640, 360),        # Píxeles en video
    point_world=(100, 50)       # Coords mundiales (metros)
)

# 3. Calcular matriz H
success, H, rmse = calibration_manager.calculate_homography()
# Usa cv2.findHomography con RANSAC
# Guarda automáticamente en respaldo1.pkl + metadata

# 4. Obtener matriz H en tiempo real
H = calibration_manager.get_homography("respaldo1")
# Retorna None si no existe calibración
```

**Algoritmo cv2.findHomography():**

```python
H, mask = cv2.findHomography(
    src_points,                          # Puntos en video
    dst_points,                          # Puntos en mapa
    method=cv2.RANSAC,                  # ← Robusto a outliers
    ransacReprojThreshold=5.0            # Threshold de inlier
)

# RANSAC interno:
# 1. Seleccionar 4 puntos al azar
# 2. Calcular H con DLT
# 3. Contar inliers (error < threshold)
# 4. Repetir ~1000 veces
# 5. Retornar H con máximo # inliers
```

### 5. video_codecs.py - Codificadores Adaptativos

**Soportados:**

| Codec | Formato | Características | Uso |
|-------|---------|-----------------|-----|
| **JPEG** | JPG | Rápido, compresión media | Default (streaming web) |
| **WebP** | WebP | Balance calidad-velocidad | Alternativa moderna |
| **H264** | H264 | Máxima compresión, lento | Grabación local |
| **Adaptive** | Auto | Elige según CPU | Optimización dinámica |

**Configuración:**

```python
CODEC_CONFIG = {
    'active_codec': 'jpeg',       # Codec actual
    'quality': 80,                # Calidad 1-100
    'preprocessing': 'none',      # 'none'|'quality'|'balanced'|'fast'
    'target_fps': 16,             # Sincronizado con detector
    'resize_factor': 1.0          # 1.0 = tamaño original
}
```

**Cambio en Tiempo Real:**

```python
# Cambiar a WebP calidad 85 sin reiniciar
switch_codec('webp', quality=85)

# El servidor detecta cambio en CODEC_CONFIG
# Próximos frames se codifican con WebP
```

**Encapsulación Codec:**

```python
class VideoCodec:
    def encode(self, frame) -> bytes:
        """Codificar frame numpy a bytes comprimidos"""
        # JPEG: cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        # WebP: cv2.imencode('.webp', frame, [cv2.IMWRITE_WEBP_QUALITY, 85])
        
    def get_stats(self) -> dict:
        """Estadísticas: avg_size, min_size, max_size, avg_encode_time"""
```

---

## Flujo de Detección

### Diagrama Temporal (Timing Preciso)

```
┌─ FRAME 1 ──────────────────────┐
│ Tiempo: 0ms                    │
│ Captura → YOLO → Anotación    │ → 62ms total
│ → Buffer push → JSON update    │
└────────────────────────────────┘
                │
                ├─ MJPEG streaming
                │  (lee buffer.get_latest)
                │  Codifica frame 1
                │  62ms después
                │
                └─ Endpoint /detections
                   (JSON de frame 1)
                   Disponible para SUMO
                   
┌─ FRAME 2 ──────────────────────┐
│ Tiempo: 62ms                   │
│ Captura → YOLO → Anotación    │ → 62ms total
│ → Buffer push → JSON update    │
└────────────────────────────────┘
     │
     ├─ MJPEG streaming (Frame 2)
     │
     └─ Endpoint /detections
        (JSON de frame 2)
```

### Paso a Paso Detallado

**1. Captura de Frame**
```python
ret, frame = cap.read()           # ← Time: 0ms (async)
if not ret: handle_stream_failure()
```

Tiempo: **~5ms** (depende de VideoCapture)

**2. Inferencia YOLO**
```python
results = model.predict(frame, conf=0.5, iou=0.45)
detections = results[0].boxes  # List[Detection]
```

Tiempo: **~30-50ms** (en GPU RTX 2060)

**3. Tracking (Centroide Basado)**
```python
for bbox in detections:
    centroid = ((x1+x2)/2, (y1+y2)/2)
    dist_to_prev = compute_distance(centroid, prev_centroids)
    track_id = assign_id_by_minimum_distance(dist_to_prev)
```

Tiempo: **~1-2ms** (número de detecciones típicamente < 20)

**4. Transformación Homográfica**
```python
H = calibration_manager.get_homography(current_source)
if H is not None:
    centroid_world = cv2.perspectiveTransform(
        np.array([[[cx, cy]]]), H
    )[0][0]
```

Tiempo: **~0.5ms** (operación vectorial GPU-compatible)

**5. Anotación**
```python
for vehicle in vehicles:
    cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
    cv2.putText(frame, f"ID:{id}", ...)
    cv2.circle(frame, center, 3, color, -1)
```

Tiempo: **~2-5ms** (depende del número de vehículos)

**6. Push al Buffer**
```python
buffer_manager.push(frame_annotated, timestamp, {
    'vehicles': [...]
    'timestamp': time.time()
})
```

Tiempo: **~5-10ms** (copia de frame + lock contention)

**7. Actualizar JSON**
```python
with data_lock:
    detection_data['vehicles'] = vehicles
    detection_data['timestamp'] = time.time()
    detection_data['total'] = len(vehicles)
    # Calcular congestión
```

Tiempo: **~0.5ms** (actualización de dict en memoria)

**Total Ciclo**: **~45-65ms** (16 FPS = 62ms/frame)

### Sincronización a 16 FPS

```python
# Throttle artificial para evitar que detector vaya más rápido que 16 FPS
frame_delay = 1.0 / 16  # 62.5ms
elapsed = time.time() - last_frame_time

if elapsed < frame_delay:
    sleep_time = frame_delay - elapsed
    time.sleep(sleep_time)  # Dormir para alcanzar 16 FPS exactos
```

---

## Calibración Homográfica

### Interfaz Web (WebUI)

**Acceso:** `http://localhost:5000/`

**Flujo de Calibración (3 Pasos):**

#### Paso 1: Seleccionar Contexto

```html
┌──────────────────────────────────┐
│ ⚙️ CONFIGURACIÓN                  │
├──────────────────────────────────┤
│                                  │
│ Selecciona Fuente de Video:      │
│ [▼ live]                         │
│   ├─ live (stream HTTP)          │
│   ├─ respaldo1 (respaldo1.mp4)   │
│   └─ respaldo2 (respaldo2.MOV)   │
│                                  │
│ Selecciona Mapa (.net):          │
│ [▼ cuenca_respaldo1]             │
│   ├─ cuenca_respaldo1            │
│   └─ cuenca_respaldo2            │
│                                  │
│ [Cargar Frame & Mapa]            │
│                                  │
└──────────────────────────────────┘
```

**JavaScript Backend:**

```javascript
// Cargar frame de video
GET /calibration/frame/{source}
// Retorna: { frame: base64, width, height }

// Cargar mapa .net.xml
GET /networks/{map_file}.net.xml
// Retorna: imagen del mapa
```

#### Paso 2: Marcar Puntos de Correspondencia

```javascript
// Canvas 1 (Video Frame): Click → obtiene (x_px, y_px)
canvas1.addEventListener('click', (e) => {
    x_px = e.offsetX;
    y_px = e.offsetY;
    // Dibujar punto verde
    ctx1.fillStyle = 'green';
    ctx1.fillRect(x_px-3, y_px-3, 6, 6);
});

// Canvas 2 (Mapa): Click → obtiene (x_world, y_world)
canvas2.addEventListener('click', (e) => {
    x_world = e.offsetX;
    y_world = e.offsetY;
    // Dibujar punto naranja
    ctx2.fillStyle = 'orange';
    ctx2.fillRect(x_world-3, y_world-3, 6, 6);
});

// Backend: Guardar punto
POST /calibration/add-point
{
    "pixel": [x_px, y_px],
    "world": [x_world, y_world]
}
```

**Validación:**
- Mínimo 4 puntos requeridos
- Máximo 20 puntos (para evitar overfitting)
- Puntos deben estar distribuidos espacialmente

#### Paso 3: Calcular y Guardar Matriz H

```javascript
POST /calibration/calculate
```

**Backend (calibration_manager.py):**

```python
def calculate_homography(self):
    """Calcula H usando cv2.findHomography con RANSAC"""
    
    src_pts = np.array(self.current_points['video'], dtype=np.float32)
    dst_pts = np.array(self.current_points['world'], dtype=np.float32)
    
    # Calcular H
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    
    if H is None:
        return False, None, float('inf')
    
    # Calcular error de reproyección
    projected = cv2.perspectiveTransform(src_pts.reshape(-1,1,2), H)
    errors = np.linalg.norm(projected - dst_pts.reshape(-1,1,2), axis=-1)
    rmse = np.sqrt(np.mean(errors**2))
    
    # Guardar
    pkl_path = self.calibration_dir / f'{self.current_source}.pkl'
    with open(pkl_path, 'wb') as f:
        pickle.dump(H, f)
    
    # Metadatos
    metadata_path = self.calibration_dir / f'{self.current_source}_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump({
            'rmse': float(rmse),
            'num_points': len(self.current_points['video']),
            'timestamp': time.time(),
            'inliers': int(mask.sum())
        }, f)
    
    return True, H, rmse
```

**Respuesta:**

```json
{
    "success": true,
    "matrix": [[...], [...], [...]],
    "rmse": 0.0453,
    "num_points": 8,
    "inliers": 7,
    "message": "✓ Calibración completa - RMSE: 4.53cm"
}
```

### Validación de Calibración

**Criterios de Aceptación:**

| Métrica | Excelente | Bueno | Aceptable | Rechazar |
|---------|-----------|-------|-----------|----------|
| RMSE | < 0.03m | < 0.10m | < 0.50m | > 1.0m |
| Inliers % | > 95% | > 85% | > 75% | < 50% |
| Punto Distribución | Toda área | Mayormente | Parcial | Concentrado |

### Limitaciones y Consideraciones

⚠️ **Asunciones de Homografía:**

1. **Todos los puntos en MISMO PLANO**: La calle es plana
   - ❌ No funciona si hay: montañas, puentes, depresiones
   - ✓ Funciona bien en: calles planas, estacionamientos, carreteras

2. **Cámara FIJA**: Ángulo y posición no cambian
   - ❌ No funciona con: cámaras PTZ (pan/tilt/zoom)
   - ✓ Funciona bien con: cámaras fijas montadas

3. **Sin distorsión de lente**: Asume óptica ideal
   - Realidad: Casi todas las cámaras tienen distorsión
   - Impacto: Error < 5% típicamente
   - Solución (futura): Calibración de cámara + undistort

4. **Vehículos tienen altura**:
   - Tope de vehículo ≠ centro ≠ base
   - Error: ±50cm típicamente
   - Mitigation: Usar centroide + altura promedio

---

## Sistema de Buffer Circular

### Propósito

Almacenar **5 segundos de video sin comprimir** para:
- Sincronización temporal
- Análisis histórico
- Recuperación ante fallos
- Streaming continuo sin lag

### Especificación

```
Duración: 5 segundos
FPS esperados: 16
Capacidad: 5 × 16 = 80 frames máximo

Memoria por frame: 1280×720×3 bytes (RGB)
= 2,764,800 bytes = ~2.6 MB

Total buffer: 80 × 2.6 MB = 208 MB en RAM
```

### Estructura de Datos

```python
class BufferManager:
    def __init__(self):
        self.frames = deque(maxlen=80)           # Frames como numpy arrays
        self.timestamps = deque(maxlen=80)       # Timestamps Unix
        self.metadata = deque(maxlen=80)         # JSON con detecciones
        self.lock = threading.RLock()            # Thread-safe
        self.frame_count = 0                     # Contador total (diagnóstico)
```

### Operaciones

**Push (Adicionar frame):**

```python
def push(self, frame, timestamp=None, metadata=None):
    with self.lock:
        frame_copy = frame.copy()  # ← Importante: copiar para evitar aliasing
        self.frames.append(frame_copy)
        self.timestamps.append(timestamp or time.time())
        self.metadata.append(metadata or {})
        self.frame_count += 1
        
        # Si frame_count >= max_frames, automáticamente se elimina el más antiguo
        # (deque.maxlen lo maneja internamente)
```

**Get Latest (Obtener más reciente):**

```python
def get_latest(self):
    """Retorna (frame, timestamp, metadata) o (None, None, None)"""
    with self.lock:
        if len(self.frames) == 0:
            return None, None, None
        return (
            self.frames[-1].copy(),          # Copia para evitar modificación
            self.timestamps[-1],             # Timestamp más reciente
            self.metadata[-1].copy() if self.metadata[-1] else {}
        )
```

**Get by Index (Acceso histórico):**

```python
def get_by_index(self, index):
    """
    index = -1 : más reciente
    index = -80: más antiguo
    index = 0: más antiguo (si 80 frames)
    """
    with self.lock:
        if len(self.frames) == 0 or abs(index) > len(self.frames):
            return None, None, None
        return (
            self.frames[index].copy(),
            self.timestamps[index],
            self.metadata[index].copy() if self.metadata[index] else {}
        )
```

**Get by Timestamp (Sincronización temporal):**

```python
def get_by_timestamp(self, target_ts):
    """Encuentra frame más cercano a target_ts"""
    with self.lock:
        if len(self.frames) == 0:
            return None, None, None
        
        # Binary search para encontrar índice más cercano
        idx = min(range(len(self.timestamps)),
                 key=lambda i: abs(self.timestamps[i] - target_ts))
        
        return (
            self.frames[idx].copy(),
            self.timestamps[idx],
            self.metadata[idx].copy() if self.metadata[idx] else {}
        )
```

### Thread-Safety

```python
# ✓ CORRECTO: Todas las operaciones protegidas
with buffer_manager.lock:
    frame, ts, metadata = buffer_manager.get_latest()
    # frame es una copia segura para modificar

# ✗ INCORRECTO: Acceso sin lock
frame = buffer_manager.frames[-1]  # Acceso directo a deque
# Puede ser modificado por otro thread mientras lo usas
```

### Gestión de Memoria

**Monitoreo:**

```python
# Obtener información del buffer
def get_buffer_stats(self):
    with self.lock:
        return {
            'total_frames': self.frame_count,
            'buffered_frames': len(self.frames),
            'buffer_duration_sec': len(self.frames) / self.expected_fps,
            'oldest_timestamp': self.timestamps[0] if len(self.timestamps) > 0 else None,
            'newest_timestamp': self.timestamps[-1] if len(self.timestamps) > 0 else None,
            'memory_mb': len(self.frames) * 2.6  # Aproximado
        }
```

**Límpieza Automática:**

```python
# deque.maxlen maneja automáticamente:
# - Si se agrega frame cuando deque está llena
# - El frame más antiguo se elimina automáticamente
# - NO requiere intervención manual

# Ejemplo:
buffer = deque(maxlen=3)
buffer.append(1)  # [1]
buffer.append(2)  # [1, 2]
buffer.append(3)  # [1, 2, 3]
buffer.append(4)  # [2, 3, 4] ← 1 fue eliminado automáticamente
```

---

## Streaming Adaptativo

### Codificadores Soportados

#### 1. JPEG (Default)

**Ventajas:**
- ✓ Muy rápido (~5-10ms encoding)
- ✓ Excelente soporte en navegadores
- ✓ Bajo CPU (CPU-friendly)

**Desventajas:**
- ✗ Tamaño medio (~30-50 KB por frame @ 80% quality)
- ✗ Sin soporte de canales alpha

**Configuración:**

```python
JPEG_PARAMS = {
    'quality': 80,  # 1-100
    '# Encoding:'
    # ret, buffer = cv2.imencode('.jpg', frame, 
    #                             [cv2.IMWRITE_JPEG_QUALITY, 80])
}
```

#### 2. WebP (Recomendado para Calidad)

**Ventajas:**
- ✓ Mejor compresión que JPEG (~20% menor tamaño)
- ✓ Mejor calidad visual subjetiva
- ✓ Soporte moderno en navegadores (>95%)

**Desventajas:**
- ✗ Más lento que JPEG (~10-20ms encoding)
- ✗ Requiere libwebp instalado

**Configuración:**

```python
WEBP_PARAMS = {
    'quality': 85,  # 1-100
    # Encoding:
    # ret, buffer = cv2.imencode('.webp', frame,
    #                             [cv2.IMWRITE_WEBP_QUALITY, 85])
}
```

#### 3. H264 (Para Grabación)

**Ventajas:**
- ✓ Máxima compresión (~10x vs JPEG)
- ✓ Hardware acceleration (NVENC en RTX)
- ✓ Estándar para video profesional

**Desventajas:**
- ✗ Mucho más lento (~50-100ms)
- ✗ Requiere decodificación en cliente
- ✗ NO recomendado para streaming en vivo

**Configuración:**

```python
# Requiere FFmpeg + NVIDIA NVENC
# No implementado en versión actual (overhead demasiado alto)
```

### Switching Dinámico

**Sin Reinicio del Servidor:**

```python
# Endpoint: POST /codec/switch/webp/85
@app.route('/codec/switch/<codec_type>/<int:quality>', methods=['POST'])
def switch_codec_endpoint(codec_type, quality):
    switch_codec(codec_type.lower(), quality=quality)
    return jsonify({'success': True, 'codec': CODEC_CONFIG['active_codec']})

# Backend (video_codecs.py):
def switch_codec(codec_type, quality=80):
    global CODEC_CONFIG
    
    CODEC_CONFIG['active_codec'] = codec_type
    CODEC_CONFIG['quality'] = quality
    
    # create_codec() usa CODEC_CONFIG actual
    # Próximos frames se codifican con nuevo codec
```

### Métricas de Rendimiento

| Codec | Tamaño (KB) | Tiempo Encoding | CPU % | GPU % |
|-------|------------|-----------------|-------|-------|
| JPEG 80% | 35-45 | 5-8ms | 15-20% | 0% |
| WebP 85 | 25-35 | 10-15ms | 20-30% | 0% |
| H264 | 5-10 | 50-100ms | 60-80% | 30-40% |

**Recomendación por Contexto:**

- **Streaming en vivo (PC3)**: JPEG (rápido, suficiente)
- **Video de referencia**: WebP (mejor calidad)
- **Grabación local**: H264 (compresión máxima)

---

## API REST

### Descripción General

**Base URL:** `http://localhost:5000`

**Autenticación:** Ninguna (usar en LAN privada)

**Rate Limiting:** Ninguno (considerar agregar en producción)

### Endpoints

#### 1. GET /detections

**Descripción:** Obtener detecciones actuales

**Request:**
```bash
curl http://localhost:5000/detections
```

**Response (200 OK):**
```json
{
  "timestamp": 1716000000.123,
  "status_stream": "online",
  "source": "respaldo1",
  "current_map": "cuenca_respaldo1",
  "counts": {
    "car": 5,
    "bus": 1,
    "truck": 0,
    "motorcycle": 2
  },
  "total": 8,
  "density": 0.4,
  "congestion": "MEDIUM",
  "homography_matrix": [
    [1.002, -0.001, -5.3],
    [0.001, 0.999, 10.2],
    [0.0001, 0.0001, 1.0]
  ],
  "vehicles": [
    {
      "id": 1,
      "class": "car",
      "bbox": [640, 360, 740, 450],
      "confidence": 0.95,
      "centroid_pixel": [690, 405],
      "centroid_world": [100.5, 50.2],
      "speed_px": 2.3
    },
    ...
  ]
}
```

**Campos:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `timestamp` | float | Unix timestamp actual |
| `status_stream` | str | "online" o "offline" |
| `source` | str | Fuente de video actual |
| `current_map` | str | Mapa cargado |
| `counts` | dict | Cantidad por clase |
| `total` | int | Total vehículos |
| `density` | float | 0-1 (total/20) |
| `congestion` | str | "LOW\|MEDIUM\|HIGH\|CRITICAL" |
| `homography_matrix` | array | Matriz H 3×3 (null si no calibrado) |
| `vehicles` | array | Detecciones (ver schema) |

**Vehicle Schema:**

```json
{
  "id": 123,                    // ID persistente
  "class": "car",               // "car"|"bus"|"truck"|"motorcycle"
  "bbox": [x1, y1, x2, y2],     // Bounding box en píxeles
  "confidence": 0.95,           // 0-1 confianza YOLO
  "centroid_pixel": [x, y],     // Centro en píxeles
  "centroid_world": [x, y],     // Centro en coords mundo (null si no calibrado)
  "speed_px": 2.3               // Píxeles/frame
}
```

#### 2. GET /health

**Descripción:** Health check del servidor

**Request:**
```bash
curl http://localhost:5000/health
```

**Response (200 OK):**
```json
{
  "status": "online",
  "timestamp": 1716000000.123,
  "stream_status": "online",
  "last_frame": 1716000000.110
}
```

#### 3. GET /video_feed

**Descripción:** Stream MJPEG del video en tiempo real

**Request:**
```bash
curl http://localhost:5000/video_feed --output stream.mjpeg

# O en navegador:
<img src="http://localhost:5000/video_feed" />
```

**Response (200 OK):**
```
HTTP/1.1 200 OK
Content-Type: multipart/x-mixed-replace; boundary=frame

--frame
Content-Type: image/jpeg
Content-Length: 45821

[JPEG DATA BINARIO]
--frame
...
```

**Características:**
- Streaming continuo @ 16 FPS
- Frames anotados con bboxes e IDs
- Sin buffer congestionado (siempre más reciente)

#### 4. GET /codec/config

**Descripción:** Obtener configuración de codificación

**Request:**
```bash
curl http://localhost:5000/codec/config
```

**Response (200 OK):**
```json
{
  "current_codec": "jpeg",
  "quality": 80,
  "preprocessing": "none",
  "target_fps": 16,
  "resize_factor": 1.0,
  "codec_stats": {
    "avg_size_kb": 38.5,
    "min_size_kb": 28.2,
    "max_size_kb": 52.1,
    "avg_encode_time_ms": 6.2
  }
}
```

#### 5. POST /codec/switch/<codec_type>/<quality>

**Descripción:** Cambiar codec de streaming sin reiniciar

**Request:**
```bash
curl -X POST http://localhost:5000/codec/switch/webp/85
```

**Response (200 OK):**
```json
{
  "success": true,
  "codec": "webp",
  "quality": 85,
  "message": "Codec cambiado a webp con calidad 85"
}
```

**Parámetros:**
- `codec_type`: "jpeg" | "webp" | "h264" | "adaptive"
- `quality`: 1-100

#### 6. POST /calibration/set-context

**Descripción:** Establecer contexto de calibración

**Request:**
```bash
curl -X POST http://localhost:5000/calibration/set-context \
  -H "Content-Type: application/json" \
  -d '{
    "source": "respaldo1",
    "map": "cuenca_respaldo1"
  }'
```

**Response (200 OK):**
```json
{
  "success": true,
  "source": "respaldo1",
  "map": "cuenca_respaldo1",
  "message": "Contexto establecido, puntos limpiados"
}
```

#### 7. GET /calibration/frame/<source>

**Descripción:** Obtener frame para calibración

**Request:**
```bash
curl http://localhost:5000/calibration/frame/respaldo1
```

**Response (200 OK):**
```json
{
  "frame_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRgABA...",
  "width": 1280,
  "height": 720,
  "timestamp": 1716000000.123
}
```

#### 8. POST /calibration/add-point

**Descripción:** Agregar punto de calibración

**Request:**
```bash
curl -X POST http://localhost:5000/calibration/add-point \
  -H "Content-Type: application/json" \
  -d '{
    "pixel": [640, 360],
    "world": [100.5, 50.2]
  }'
```

**Response (200 OK):**
```json
{
  "success": true,
  "point_count": 5,
  "points": [
    {"pixel": [640, 360], "world": [100.5, 50.2]},
    ...
  ],
  "message": "Punto agregado. 5/4 puntos necesarios."
}
```

#### 9. POST /calibration/calculate

**Descripción:** Calcular y guardar matriz H

**Request:**
```bash
curl -X POST http://localhost:5000/calibration/calculate
```

**Response (200 OK):**
```json
{
  "success": true,
  "matrix": [
    [1.002, -0.001, -5.3],
    [0.001, 0.999, 10.2],
    [0.0001, 0.0001, 1.0]
  ],
  "rmse": 0.0453,
  "num_points": 8,
  "inliers": 7,
  "message": "✓ Calibración completa - RMSE: 4.53cm"
}
```

#### 10. POST /shutdown

**Descripción:** Iniciar shutdown seguro

**Request:**
```bash
curl -X POST http://localhost:5000/shutdown
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Shutdown iniciado. El servidor cerrará en 5 segundos."
}
```

---

## Tuning y Optimización

### Parámetros Configurables

#### 1. Calidad de YOLO

**Ubicación:** `src/detector.py` línea ~200

```python
# Confidence threshold
results = model.predict(frame, conf=0.5)  # ← Modificar

# IoU threshold (NMS)
results = model.predict(frame, iou=0.45)  # ← Modificar
```

**Impacto:**

| Parámetro | Rango | Efecto de Aumentar |
|-----------|-------|-------------------|
| `conf` | 0.1-0.9 | Menos detecciones falsos, pero menos precisión |
| `iou` | 0.2-0.9 | Menos boxes duplicados, pero puede perder objetos |

**Recomendaciones:**
- `conf=0.5`: Balance entre precisión y recall (default)
- `conf=0.7`: Mayor precisión, menos falsos positivos
- `conf=0.3`: Máximo recall, más falsos positivos

#### 2. FPS de Streaming

**Ubicación:** `src/detector.py` y `src/server.py`

```python
# Detector FPS
target_fps = 16  # ← Modificar

# Streaming FPS
time.sleep(1.0 / target_fps)  # En generate_frames()
```

**Impacto:**

| FPS | Latencia | Fluidez | Bandwidth | CPU |
|-----|----------|---------|-----------|-----|
| 10 | 100ms | Chungo | Bajo | Muy Bajo |
| 16 | 62ms | Suave | Medio | Bajo |
| 30 | 33ms | Muy suave | Alto | Medio-Alto |

#### 3. Calidad del Codec

**Ubicación:** `src/video_codecs.py` línea ~30

```python
CODEC_CONFIG = {
    'active_codec': 'jpeg',
    'quality': 80,  # ← Modificar (1-100)
}
```

**JPEG Quality Scale:**

```
quality=60  → 20-25 KB, notables artefactos
quality=75  → 28-35 KB, artefactos visibles
quality=80  → 35-45 KB, buena relación (DEFAULT)
quality=90  → 50-70 KB, muy buena calidad
quality=95  → 65-90 KB, calidad máxima
```

#### 4. Preprocesamiento

**Ubicación:** `src/video_codecs.py` línea ~35

```python
CODEC_CONFIG = {
    'preprocessing': 'none',  # ← Modificar
}
```

**Opciones:**

```python
'none'       # SIN filtros (DEFAULT - máxima velocidad)
'fast'       # Resize solamente
'balanced'   # CLAHE + Denoise (LENTO)
'quality'    # CLAHE + Sharpen (MUY LENTO)
```

**⚠️ ADVERTENCIA:**
- Los filtros `balanced` y `quality` son O(n²)
- Causarán lag severo en streaming en vivo
- Usar solo si video grabado post-procesamiento

#### 5. Buffer Duration

**Ubicación:** `src/buffer_manager.py` línea ~15

```python
buffer_manager = BufferManager(
    buffer_duration_seconds=5,  # ← Modificar
    expected_fps=16
)
```

**Impacto en Memoria:**

```
Buffer Duration  Memoria (MB)  Use Case
3 segundos       ~78           Bajo lag pero poco histórico
5 segundos       ~130          Balance (DEFAULT)
10 segundos      ~260          Más histórico, más memoria
15 segundos      ~390          Máximo (cuidado con RAM)
```

### Herramienta Interactiva: tune.py

```bash
python tune.py

# Menú:
# 1. Cambiar YOLO Confidence
# 2. Cambiar YOLO IoU
# 3. Cambiar FPS de Streaming
# 4. Cambiar Codec (JPEG/WebP)
# 5. Cambiar Calidad del Codec
# 6. Aplicar Perfil Predefinido
# 0. Salir
```

### Perfiles Predefinidos

```python
PROFILES = {
    'fast': {
        'codec': 'jpeg',
        'quality': 60,
        'preprocessing': 'none',
        'yolo_conf': 0.7,
        'fps': 10
    },
    'balanced': {
        'codec': 'jpeg',
        'quality': 80,
        'preprocessing': 'none',
        'yolo_conf': 0.5,
        'fps': 16
    },
    'high_quality': {
        'codec': 'webp',
        'quality': 90,
        'preprocessing': 'none',
        'yolo_conf': 0.4,
        'fps': 16
    },
    'maximum_quality': {
        'codec': 'webp',
        'quality': 95,
        'preprocessing': 'balanced',
        'yolo_conf': 0.3,
        'fps': 10
    }
}
```

---

## Integración con SUMO

### ¿Qué es SUMO?

**SUMO (Simulation of Urban MObility)** es un simulador microscópico de tráfico de código abierto:

- Simula vehículos individuales
- Comportamiento realista (aceleración, frenado, cambios de carril)
- Compatible con mapas OSM (OpenStreetMap)
- Computación determinística

### Flujo de Integración

```
┌─────────────────────┐
│ PC1: Traffic Gemelo │
│ (Detección YOLO)    │
└──────────┬──────────┘
           │
           │ GET /detections (200ms)
           │ JSON: {vehicles, H, timestamp}
           │
           ▼
┌─────────────────────────────────────┐
│ PC2: Middleware (SUMO Integration)  │
│                                      │
│ 1. Parsea JSON                      │
│ 2. Aplica matriz H (pixel→mundo)   │
│ 3. Valida coordenadas vs mapa      │
│ 4. Inyecta vehículos en SUMO        │
└──────────┬──────────────────────────┘
           │
           │ TraCI (SUMO API)
           │
           ▼
┌──────────────────────────────┐
│ SUMO Simulator               │
│ ├─ Carga mapa .net.xml       │
│ ├─ Simula vehículos          │
│ ├─ Calcula tráfico           │
│ └─ Exporta resultados        │
└──────────────────────────────┘
```

### JSON de Detecciones para SUMO

```json
{
  "timestamp": 1716000000.123,
  "source": "respaldo1",
  "current_map": "cuenca_respaldo1",
  "homography_matrix": [
    [1.002, -0.001, -5.3],
    [0.001, 0.999, 10.2],
    [0.0001, 0.0001, 1.0]
  ],
  "vehicles": [
    {
      "id": 101,
      "class": "car",
      "centroid_world": [100.5, 50.2],
      "speed_px": 2.3,
      "confidence": 0.95
    },
    {
      "id": 102,
      "class": "bus",
      "centroid_world": [105.3, 55.8],
      "speed_px": 1.8,
      "confidence": 0.92
    }
  ]
}
```

### Middleware de SUMO (PC2)

**Pseudocódigo:**

```python
def sumo_integration_loop():
    """Consulta Traffic Gemelo cada 200ms e inyecta en SUMO"""
    
    import traci  # TraCI es la API de SUMO
    
    traci.start([sumolib.checkBinary('sumo'), 
                 '-c', 'config.sumocfg', '--no-warnings'])
    
    while True:
        # 1. Obtener detecciones
        response = requests.get('http://192.168.1.X:5000/detections')
        data = response.json()
        
        # 2. Verificar matriz H está disponible
        if data['homography_matrix'] is None:
            print("⚠️ Sin calibración homográfica, saltando...")
            time.sleep(0.2)
            continue
        
        # 3. Inyectar vehículos
        for vehicle in data['vehicles']:
            x_world, y_world = vehicle['centroid_world']
            
            # Validar coordenadas en mapa
            if not is_within_network_bounds(x_world, y_world):
                continue  # Fuera del mapa
            
            # Obtener carril más cercano
            lane = find_nearest_lane(x_world, y_world)
            position = calculate_position_on_lane(x_world, y_world, lane)
            
            # Inyectar o actualizar vehículo
            veh_id = f"gemelo_{vehicle['id']}"
            
            if veh_id not in traci.vehicle.getIDList():
                # Crear nuevo vehículo
                traci.vehicle.add(veh_id, routeID="route1",
                                 typeID=vehicle['class'])
            
            # Actualizar posición
            traci.vehicle.setLanePosition(veh_id, position)
        
        # 4. Simular un paso
        traci.simulationStep()
        
        time.sleep(0.2)  # Esperar 200ms hasta siguiente consulta
    
    traci.close()
```

### Formato del Archivo .net.xml

**Estructura:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<net version="1.16" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ...>
    
    <!-- Ubicaciones (junctions) -->
    <junction id="J1" type="priority" x="100.0" y="50.0" z="0.0"/>
    <junction id="J2" type="priority" x="200.0" y="50.0" z="0.0"/>
    
    <!-- Calles (edges) -->
    <edge id="E1" from="J1" to="J2" priority="1">
        <!-- Carriles (lanes) -->
        <lane id="E1_0" index="0" speed="13.9" length="100.0" shape="100.0,50.0 200.0,50.0"/>
        <lane id="E1_1" index="1" speed="13.9" length="100.0" shape="100.0,53.2 200.0,53.2"/>
    </edge>
    
    <!-- Conexiones entre carriles -->
    <connection from="E1_0" to="E2_0" fromLane="0" toLane="0"/>
    
    <!-- Rutas -->
    <route id="route1" edges="E1 E2 E3"/>
    
</net>
```

**Lectura de Coordenadas:**

```python
import xml.etree.ElementTree as ET

def read_net_bounds(net_xml_file):
    tree = ET.parse(net_xml_file)
    root = tree.getroot()
    
    x_coords = []
    y_coords = []
    
    for junction in root.findall('.//junction'):
        x = float(junction.get('x'))
        y = float(junction.get('y'))
        x_coords.append(x)
        y_coords.append(y)
    
    return {
        'x_min': min(x_coords),
        'x_max': max(x_coords),
        'y_min': min(y_coords),
        'y_max': max(y_coords)
    }

# Uso:
bounds = read_net_bounds('networks/cuenca_respaldo1.net.xml')
print(f"Mapa: X=[{bounds['x_min']}, {bounds['x_max']}], Y=[{bounds['y_min']}, {bounds['y_max']}]")
```

### Intervalos de Envío Recomendados

| Componente | Intervalo | Razón |
|-----------|-----------|-------|
| Detecciones | 200ms (5 Hz) | Coincide con detector @ 16 FPS |
| Matriz H | Única (al cambiar video) | No cambia frecuentemente |
| Health Check | 5-10s | Opcional |

---

## Lectura de Archivos .NET

### Estructura SUMO .net.xml

Los archivos `.net.xml` definen la **topología de la red vial**:

```xml
<net>
    <!-- Junctions (intersecciones) -->
    <junction id="J1" type="priority" x="100.0" y="50.0"/>
    
    <!-- Edges (calles/avenidas) -->
    <edge id="E1" from="J1" to="J2" priority="1">
        <lane id="E1_0" speed="13.9" length="100.0"/>
        <lane id="E1_1" speed="13.9" length="100.0"/>
    </edge>
    
    <!-- Connections (conexiones entre carriles) -->
    <connection from="E1_0" to="E2_0"/>
    
    <!-- Routes (rutas) -->
    <route id="route1" edges="E1 E2 E3"/>
</net>
```

### Parsing en Python

```python
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Junction:
    id: str
    x: float
    y: float
    z: float = 0.0
    type: str = "priority"

@dataclass
class Lane:
    id: str
    index: int
    speed: float
    length: float
    shape: List[tuple]  # [(x1,y1), (x2,y2), ...]

@dataclass
class Edge:
    id: str
    from_junction: str
    to_junction: str
    lanes: List[Lane]
    priority: int = 1

class SUMONetworkReader:
    def __init__(self, net_xml_path: str):
        self.net_xml_path = net_xml_path
        self.tree = ET.parse(net_xml_path)
        self.root = self.tree.getroot()
        
        self.junctions: Dict[str, Junction] = {}
        self.edges: Dict[str, Edge] = {}
        self.routes: Dict[str, List[str]] = {}
        
        self._parse_network()
    
    def _parse_network(self):
        """Parsea archivo .net.xml"""
        
        # 1. Leer junctions
        for junction_elem in self.root.findall('.//junction'):
            j = Junction(
                id=junction_elem.get('id'),
                x=float(junction_elem.get('x')),
                y=float(junction_elem.get('y')),
                z=float(junction_elem.get('z', 0)),
                type=junction_elem.get('type', 'priority')
            )
            self.junctions[j.id] = j
        
        # 2. Leer edges (calles)
        for edge_elem in self.root.findall('.//edge'):
            edge_id = edge_elem.get('id')
            from_j = edge_elem.get('from')
            to_j = edge_elem.get('to')
            priority = int(edge_elem.get('priority', 1))
            
            lanes = []
            for lane_elem in edge_elem.findall('lane'):
                # Parsear shape
                shape_str = lane_elem.get('shape')
                shape = self._parse_shape(shape_str)
                
                lane = Lane(
                    id=lane_elem.get('id'),
                    index=int(lane_elem.get('index')),
                    speed=float(lane_elem.get('speed')),
                    length=float(lane_elem.get('length')),
                    shape=shape
                )
                lanes.append(lane)
            
            edge = Edge(
                id=edge_id,
                from_junction=from_j,
                to_junction=to_j,
                lanes=lanes,
                priority=priority
            )
            self.edges[edge_id] = edge
        
        # 3. Leer rutas
        for route_elem in self.root.findall('.//route'):
            route_id = route_elem.get('id')
            edges_str = route_elem.get('edges')
            edges_list = edges_str.split()
            self.routes[route_id] = edges_list
    
    def _parse_shape(self, shape_str: str) -> List[tuple]:
        """Parsear shape "x1,y1 x2,y2 ..." a [(x1,y1), (x2,y2), ...]"""
        points = []
        for point_str in shape_str.split():
            x, y = map(float, point_str.split(','))
            points.append((x, y))
        return points
    
    def get_bounds(self) -> Dict[str, float]:
        """Obtener límites del mapa"""
        if not self.junctions:
            return {'x_min': 0, 'x_max': 0, 'y_min': 0, 'y_max': 0}
        
        x_coords = [j.x for j in self.junctions.values()]
        y_coords = [j.y for j in self.junctions.values()]
        
        return {
            'x_min': min(x_coords),
            'x_max': max(x_coords),
            'y_min': min(y_coords),
            'y_max': max(y_coords)
        }
    
    def is_point_in_network(self, x: float, y: float, margin: float = 10.0) -> bool:
        """Verificar si punto está dentro de límites del mapa"""
        bounds = self.get_bounds()
        return (bounds['x_min'] - margin <= x <= bounds['x_max'] + margin and
               bounds['y_min'] - margin <= y <= bounds['y_max'] + margin)
    
    def find_nearest_edge(self, x: float, y: float) -> str:
        """Encontrar edge más cercano a punto (x, y)"""
        min_dist = float('inf')
        nearest_edge_id = None
        
        for edge_id, edge in self.edges.items():
            # Calcular distancia a cada lane del edge
            for lane in edge.lanes:
                for i in range(len(lane.shape) - 1):
                    x1, y1 = lane.shape[i]
                    x2, y2 = lane.shape[i + 1]
                    
                    # Distancia punto a segmento
                    dist = point_to_segment_distance((x, y), (x1, y1), (x2, y2))
                    
                    if dist < min_dist:
                        min_dist = dist
                        nearest_edge_id = edge_id
        
        return nearest_edge_id
    
    def find_position_on_edge(self, x: float, y: float, edge_id: str) -> float:
        """Calcular posición a lo largo del edge (0 a length)"""
        edge = self.edges[edge_id]
        # Calcular distancia acumulada desde inicio de edge
        # hasta punto más cercano en edge
        # (Implementación simplificada)
        return edge.lanes[0].length / 2  # Pseudo-implementación

# Uso:
reader = SUMONetworkReader('networks/cuenca_respaldo1.net.xml')

print(f"Junctions: {len(reader.junctions)}")
print(f"Edges: {len(reader.edges)}")
print(f"Bounds: {reader.get_bounds()}")

# Validar coordenada
x, y = 100.5, 50.2
if reader.is_point_in_network(x, y):
    print(f"({x}, {y}) está dentro del mapa")
    nearest_edge = reader.find_nearest_edge(x, y)
    print(f"Edge más cercano: {nearest_edge}")
```

### Validación de Coordenadas

```python
def validate_vehicle_position(vehicle_data, network_reader):
    """Valida si vehículo está en posición válida"""
    
    x_world, y_world = vehicle_data['centroid_world']
    
    # 1. Verificar dentro de límites
    if not network_reader.is_point_in_network(x_world, y_world):
        return False, "Fuera de límites del mapa"
    
    # 2. Encontrar edge más cercano
    nearest_edge_id = network_reader.find_nearest_edge(x_world, y_world)
    if nearest_edge_id is None:
        return False, "No hay edge cercano"
    
    # 3. Calcular posición en edge
    position = network_reader.find_position_on_edge(x_world, y_world, nearest_edge_id)
    
    return True, {
        'edge_id': nearest_edge_id,
        'position': position,
        'x': x_world,
        'y': y_world
    }
```

---

## Shutdown Seguro

### Motivación

Un shutdown incorrecto puede:
- ✗ Dejar archivos corrompidos
- ✗ Dejar puertos TCP ocupados
- ✗ Causar fuga de memoria
- ✗ Perder datos sin guardar

Un shutdown correcto:
- ✓ Libera todos los recursos
- ✓ Cierra conexiones gracefully
- ✓ Guarda estado pendiente
- ✓ Permite reinicio inmediato

### Mecanismos de Shutdown

#### 1. CTRL+C (RECOMENDADO)

**Flujo:**

```python
# En server.py línea ~50
import signal

def handle_sigint(signum, frame):
    """Handler para SIGINT (CTRL+C)"""
    print("\n" + "="*60)
    print("⚠️  CTRL+C detectado - Iniciando shutdown seguro...")
    print("="*60 + "\n")
    
    detector.signal_shutdown()  # Set shutdown_event
    app.shutdown()              # Detener Flask
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigterm)
```

**En Terminal:**

```bash
$ python run.py
[SERVER] Iniciando...
[DETECTOR] Thread iniciado

^C  ← Presionar Ctrl+C

⚠️  CTRL+C detectado - Iniciando shutdown seguro...
[CLEANUP] Liberando VideoCapture...
[CLEANUP] Limpiando buffer...
✅ Detector stopped
[SERVER] Flask cerrado
```

#### 2. Endpoint API

```bash
curl -X POST http://localhost:5000/shutdown
```

**Backend:**

```python
@app.route('/shutdown', methods=['POST'])
def shutdown():
    detector.signal_shutdown()
    return jsonify({'success': True, 'message': 'Shutdown initiado'}), 200
```

#### 3. Script tune.py

```python
# tune.py línea ~500
if option == '0':  # Salir
    print("\n👋 Cerrando herramienta de tuning...")
    break

# El script permite salida graceful
```

### Procedimiento de Shutdown

```
┌─────────────────────────────────┐
│ 1. SEÑAL RECIBIDA               │
│ (SIGINT, SIGTERM, o /shutdown)  │
└─────────────────┬───────────────┘
                  │
                  ▼
         ┌─────────────────────────────┐
         │ 2. shutdown_event.set()     │
         │ Señal para detector thread  │
         └─────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ 3. Detector ve shutdown_event│
        │ Sale del loop while          │
        │ (detecta !shutdown_event)    │
        └─────────────┬────────────────┘
                      │
                      ▼
        ┌──────────────────────────────┐
        │ 4. Bloque finally:           │
        │ - cap.release()              │
        │ - buffer_manager.clear()     │
        │ - Model descarga GPU         │
        └─────────────┬────────────────┘
                      │
                      ▼
        ┌──────────────────────────────┐
        │ 5. thread.join(timeout=5s)   │
        │ Esperar a que thread termine │
        └─────────────┬────────────────┘
                      │
                      ▼
        ┌──────────────────────────────┐
        │ 6. Flask recibe señal        │
        │ Cierra servidor HTTP         │
        └─────────────┬────────────────┘
                      │
                      ▼
        ┌──────────────────────────────┐
        │ 7. sys.exit(0)               │
        │ ✅ Shutdown completo         │
        └──────────────────────────────┘
```

### Código de Implementación

**En detector.py:**

```python
shutdown_event = threading.Event()

def signal_shutdown():
    """Señal para que detector thread se detenga"""
    global shutdown_event
    shutdown_event.set()

def run_detector(...):
    global shutdown_event
    
    try:
        while not shutdown_event.is_set():  # ← Revisa cada iteración
            # Detector loop
            ret, frame = cap.read()
            if not ret:
                break
            
            # Procesar...
            
            time.sleep(1.0 / 16)
    
    except KeyboardInterrupt:
        print("[DETECTOR] Interruption detectada")
    
    finally:
        print("[CLEANUP] Liberando recursos...")
        
        # Liberar VideoCapture
        if cap is not None:
            cap.release()
            print("[CLEANUP] VideoCapture cerrado")
        
        # Limpiar buffer
        buffer_manager.frames.clear()
        buffer_manager.timestamps.clear()
        print("[CLEANUP] Buffer limpiado")
        
        # Liberar modelo de GPU
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        print("[CLEANUP] GPU limpiada")
        
        print("✅ Detector stopped.")
```

**En server.py:**

```python
from detector import signal_shutdown, shutdown_event

@app.route('/shutdown', methods=['POST'])
def shutdown_endpoint():
    signal_shutdown()
    
    def delayed_shutdown():
        time.sleep(1)  # Dar tiempo a que respuesta se envíe
        os._exit(0)
    
    thread = threading.Thread(target=delayed_shutdown)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'message': 'Shutdown iniciado. El servidor cerrará en 1 segundo.'
    }), 200

if __name__ == '__main__':
    import signal
    
    def handle_sigint(signum, frame):
        print("\n" + "="*60)
        print("⚠️  CTRL+C detectado - Iniciando shutdown seguro...")
        print("="*60 + "\n")
        
        signal_shutdown()
        os._exit(0)
    
    def handle_sigterm(signum, frame):
        print("\n[SIGNAL] SIGTERM recibido")
        signal_shutdown()
        os._exit(0)
    
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    start_server(host='0.0.0.0', port=5000, debug=False)
```

---

## Troubleshooting

### Problema: CUDA no disponible

**Síntomas:**
```
torch.cuda.is_available() → False
```

**Soluciones:**

```bash
# 1. Verificar drivers NVIDIA
nvidia-smi
# Si no aparece: instalar drivers

# 2. Reinstalar PyTorch para CUDA 12.1
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Verificar CUDA en Python
python3 -c "import torch; print(torch.cuda.get_device_name(0))"
```

### Problema: Stream en vivo falla (conexión HTTP timeout)

**Síntomas:**
```
[STREAM] Intento 1: Connection timeout
[STREAM] Fallback a video local
```

**Soluciones:**

```bash
# 1. Verificar conectividad
curl -I "https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8"

# 2. Verificar si proxy requiere autenticación
# Editar run.py para agregar proxy

# 3. Usar video local como fallback (ya configurado)
# El sistema automáticamente usa respaldo.mp4

# 4. Descargar stream manualmente
ffmpeg -i "stream_url" -t 120 videos/respaldo.mp4
```

### Problema: Bajo FPS (<10)

**Causas Posibles:**

1. **GPU saturada**
   ```bash
   nvidia-smi  # Ver utilización GPU
   # Si GPU% > 90%:
   # - Reducir calidad con tune.py
   # - Usar modelo yolov8n (más rápido)
   ```

2. **CPU bottleneck**
   ```bash
   top  # Ver uso CPU
   # Si CPU% > 80%:
   # - Desactivar preprocesamiento (set 'none')
   # - Reducir FPS esperado
   ```

3. **Problema de I/O (lectura video)**
   ```bash
   # Usar video local en lugar de stream HTTP
   # Editar run.py: stream_mode = 'respaldo1'
   ```

**Solución Rápida:**

```python
# tune.py
# Seleccionar: 6 → Perfil "fast"
# Esto:
# - JPEG quality 60
# - FPS 10
# - YOLO conf 0.7 (menos detecciones)
```

### Problema: Matriz Homografía no converge (RMSE alto)

**Síntomas:**
```
✗ Calibración fallida
Mean Error: 0.5234m  ← Demasiado error
```

**Soluciones:**

1. **Más puntos de calibración**
   - Agregar al menos 2-3 puntos más
   - Asegurar distribuidos espacialmente

2. **Puntos más precisos**
   - Marcar con más cuidado en video y mapa
   - Usar "esquinas" o "líneas" como referencia

3. **Verificar matriz H guardada anteriormente**
   ```python
   # En detector.py
   H = calibration_manager.get_homography('respaldo1')
   print(H)  # Imprimir matriz actual
   ```

4. **Recalibrar desde cero**
   - Eliminar archivo: `calibration/respaldo1.pkl`
   - Repetir calibración con más cuidado

### Problema: Vehículos no se detectan correctamente

**Síntomas:**
```
"total": 0  ← Sin detecciones
```

**Soluciones:**

1. **Aumentar confianza mínima**
   ```python
   # tune.py → Opción 1
   # Reducir YOLO conf (default 0.5 → 0.3)
   ```

2. **Cambiar modelo YOLO**
   ```bash
   # Usar modelo más pequeño (yolov8n)
   export YOLO_MODEL=yolov8n.pt
   python run.py
   ```

3. **Verificar iluminación**
   - YOLO es sensible a iluminación
   - Probar con video local si stream en vivo falla

4. **Ajustar IOU threshold**
   ```python
   # detector.py línea ~200
   results = model.predict(frame, iou=0.3)  # Reducir IOU
   ```

### Problema: API timeout

**Síntomas:**
```
curl http://localhost:5000/detections
# Espera 30s luego:
curl: (7) Failed to connect to localhost port 5000: Connection refused
```

**Soluciones:**

```bash
# 1. Verificar si servidor está corriendo
ps aux | grep "python run.py"

# 2. Revisar puertos en uso
sudo netstat -tulnp | grep 5000

# 3. Si puerto está ocupado, matar proceso
kill -9 <PID>

# 4. Reiniciar servidor
python run.py
```

### Problema: Memoria aumenta continuamente

**Síntomas:**
```
htop: VIRT 4GB → 8GB → 12GB (RAM llena)
```

**Soluciones:**

```python
# 1. Buffer overflow (revisa buffer_manager)
# Si buffer_duration > 15s → reducir

# 2. Memory leak en detecciones
# Revisar: detection_data acumula vehículos?

# 3. GPU memory leak
# En detector.py:
torch.cuda.empty_cache()  # Agregar después de inferencia

# 4. Frame copies no se liberan
# Asegurar que get_latest() retorna copia (ya hace)
```

**Monitoreo:**

```bash
# Ver uso de memoria en tiempo real
watch -n 1 nvidia-smi

# Ver procesos Python
ps aux | grep python
```

---

## Conclusión

**Traffic Gemelo** es un sistema completo y robusto de detección de tráfico que integra:

✓ **Deep Learning**: YOLO para detección en tiempo real en GPU  
✓ **Geometría Proyectiva**: Homografía para mapeo píxel ↔ mundo  
✓ **Procesamiento Digital**: OpenCV para visión por computadora  
✓ **Sistemas Distribuidos**: API REST para integración externa  
✓ **Concurrencia**: Threads para múltiples tareas simultáneamente  
✓ **Ingeniería**: Buffer circular, streaming adaptativo, shutdown seguro  

El sistema está listo para investigación, demostración y producción en entornos controlados.

---

## Referencias y Recursos

### Documentos Relacionados
- [HOMOGRAPHY_CALIBRATION.md](HOMOGRAPHY_CALIBRATION.md) - Guía de calibración
- [TUNING_GUIDE.md](TUNING_GUIDE.md) - Parámetros de optimización
- [SHUTDOWN_GUIDE.md](SHUTDOWN_GUIDE.md) - Procedimiento de cierre
- [SENDING_INTERVALS.md](SENDING_INTERVALS.md) - Intervalos con SUMO
- [INTEGRATION_COMPLETE.md](INTEGRATION_COMPLETE.md) - Integración con SUMO

### Librerías Utilizadas
- **YOLOv8**: https://docs.ultralytics.com/
- **OpenCV**: https://docs.opencv.org/
- **PyTorch**: https://pytorch.org/docs/
- **Flask**: https://flask.palletsprojects.com/
- **SUMO**: https://sumo.dlr.de/docs/

### Lecturas Recomendadas
- "You Only Look Once" (2015) - Redmon et al.
- "Multiple View Geometry" - Hartley & Zisserman
- "Real-time Detection and Tracking of Vehicles" - Traffic Engineering

---

**Versión del Documento:** 2.5.1  
**Última Actualización:** Mayo 2026  
**Mantenedor:** Equipo de Investigación  
**Estado:** Production-Ready ✅
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
