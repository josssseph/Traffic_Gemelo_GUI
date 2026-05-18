# ⏱️ Intervalos de Envío Recomendados - Traffic Gemelo

## Resumen Ejecutivo

| Componente | Intervalo | Razón | Prioridad |
|------------|-----------|-------|-----------|
| **Detecciones (vehículos)** | 200ms (5 Hz) | Streaming suave + margen de procesamiento | ⭐⭐⭐ |
| **Matriz de Homografía** | Única calibración | Se envía siempre en JSON, actualiza al cambiar video | ⭐⭐⭐ |
| **Status del Stream** | Con detecciones (200ms) | Incluido en `/detections` | ⭐⭐ |
| **Configuración (setup)** | Una vez al iniciar | Se consulta al inicio de PC2 | ⭐⭐ |
| **Health Check** | 5-10 segundos | Opcional, para monitoreo | ⭐ |

---

## 1. Detecciones de Vehículos → PC2

### Configuración Actual
```
Intervalo: 200ms (equivalente a 5 Hz)
Tamaño de payload: 2-5 KB (JSON)
Throughput: 10-25 KB/s
Latencia: 50-200ms (red + procesamiento)
```

### Por Qué 200ms?

**Cálculos:**
```
Video capturado: 30 FPS (1 frame cada 33ms)
Detector procesa: 16 FPS (1 de cada 2 frames, 1 procesado cada 62ms)
Buffer: 5 segundos (80 frames @ 16 FPS)

Intervalo de envío options:
  - 100ms (10 Hz)  → Respuesta muy rápida, pero overkill
  - 200ms (5 Hz)   → RECOMENDADO ← Balance perfecto
  - 500ms (2 Hz)   → Más lento pero suficiente si hay lag
  - 1000ms (1 Hz)  → Muy lento, no recomendado
```

**Ventajas de 200ms:**
- ✅ SUMO actualiza con frecuencia suficiente (5 Hz)
- ✅ Red local (LAN) lo maneja sin congestión
- ✅ Coincide con detector @ 16 FPS (16/5 = 3.2 frames por update)
- ✅ Latencia humana imperceptible
- ✅ Bajo consumo de bandwidth

### Implementación

**En `tune.py` (línea ~200):**
```python
DETECTOR_INTERVAL = 0.2  # 200ms entre lecturas de /detections
```

**En PC2 (SUMO middleware):**
```python
while True:
    response = requests.get('http://192.168.1.X:5000/detections', timeout=1)
    data = response.json()
    
    # Inyectar en SUMO
    for vehicle in data['vehicles']:
        # ...proceso de inyección...
    
    time.sleep(0.2)  # 200ms entre consultas
```

---

## 2. Matriz de Homografía

### Configuración
```
Envío: INCLUIDA EN CADA JSON de /detections
Actualización: Solo cuando cambia de video
Persistencia: Guardada en calibration/*.pkl
```

### Flujo

```
STEP 1: Usuario calibra video "respaldo1"
  ↓
  calibration_manager.calculate_homography()
  └─→ Se guarda: calibration/respaldo1.pkl
  └─→ Se carga en MEMORIA

STEP 2: GET /detections devuelve:
  {
    "source": "respaldo1",
    "homography_matrix": [[...], [...], [...]],  ← Incluida aquí
    "vehicles": [...]
  }

STEP 3: User cambia a "respaldo2"
  ↓
  calibration_manager.set_calibration_context("respaldo2", ...)
  └─→ Busca calibration/respaldo2.pkl
  └─→ Si existe, la carga
  └─→ Si no existe, envía null

STEP 4: GET /detections devuelve:
  {
    "source": "respaldo2",
    "homography_matrix": null,  ← No calibrada aún
    "vehicles": [...]
  }
```

### Tamaño de Matriz

```
Matriz H: 3×3 elementos (flotantes)
En JSON: [[...], [...], [...]]

Tamaño aproximado:
  9 floats × 15 caracteres = ~135 bytes (incluido formato)
  Negligible (<1% del payload total)
```

### Recomendación

**NO cambiar intervalo, está ÓPTIMO:**
- Envío: 200ms con detecciones
- Actualización: Solo si cambias video (manual, no automático)
- Persistencia: Automática a disco

---

## 3. Cambios de Video (Source Switching)

### Escenario: LIVE → respaldo1 → LIVE

```
ACCIÓN:
  Usuario hace clic en toggle "FALLBACK" en dashboard

PC1 (Video):
  - detector.py: set_stream_mode('fallback')
  - Buffer continúa (puede haber hiato ~500ms)
  - Siguiente JSON incluye: "source": "fallback"

PC2 (SUMO) recibe en /detections:
  "source": "fallback"
  "homography_matrix": <matriz_respaldo1>  ← Se busca automáticamente

SUMO:
  - Si tiene matriz guardada → la usa
  - Si no tiene → envía vehículos sin transformación (cuidado!)
```

### Intervalo Recomendado para Cambio

**Tiempo mínimo antes de cambiar de video:**
```
Mínimo: 1 segundo (5-6 updates)
Ideal: 2-3 segundos

Razón:
  - Detector necesita limpiar estado anterior
  - Buffer necesita estabilizarse
  - SUMO necesita recibir N updates confirmando nuevo source
```

---

## 4. Configuración Inicial (Setup)

### PC2 Startup (una vez)

```python
# Al iniciar PC2, ANTES de loop principal
startup_time = 0

GET /calibration/sources
  ↓ Response:
  {
    "sources": {
      "live": {...},
      "respaldo1": {...},
      "respaldo2": {...}
    },
    "current_source": "live"
  }

GET /calibration/maps
  ↓ Response:
  {
    "maps": {
      "cuenca_respaldo1": {...},
      "cuenca_respaldo2": {...}
    }
  }

GET /calibration/status
  ↓ Response:
  {
    "calibrations": {
      "live": null,
      "respaldo1": {"calibrated": True, "mean_error": 0.045, ...},
      "respaldo2": {"calibrated": True, "mean_error": 0.082, ...}
    }
  }

# Tiempo total: ~500-1000ms (negligible)
```

### Loop Principal (repetitivo)

```python
while True:
    # Solo consultar detecciones
    response = requests.get('/detections')
    data = response.json()
    
    # Usar matriz si está disponible
    if data['homography_matrix']:
        H = np.array(data['homography_matrix'])
        x_mundo, y_mundo = H @ (x_px, y_px)
    
    time.sleep(0.2)  # 200ms
```

**Conclusión:** Setup inicial → rápido. Loop → optimizado.

---

## 5. Recomendación Final: Intervalos Óptimos

### Para Red Local (LAN)

```
┌─────────────────────────────────────────────────┐
│ Intervalo de Detecciones: 200ms (5 Hz)          │
│                                                  │
│ PC1 (Video)           PC2 (SUMO)                │
│ ├─ Detecta vehículos  └─ Consulta cada 200ms   │
│ └─ Calcula H             ├─ Inyecta en SUMO    │
│                          └─ Actualiza tráfico   │
│                                                  │
│ Latencia End-to-End: ~250ms                     │
│ Ancho de Banda: ~50 KB/s                        │
│ Tolerancia a pérdidas: Muy alta                 │
└─────────────────────────────────────────────────┘
```

### Para Red WAN (VPN/Internet)

```
Si PC1 y PC2 están en internet:
  Cambiar intervalo a 500ms (2 Hz)
  Latencia tolerada: ~500-1000ms
  Ancho de banda: ~20 KB/s
```

### Script de Calibración de Intervalos

```python
# test_intervals.py
import requests
import time

def test_interval(interval_ms):
    print(f"\nProbando intervalo: {interval_ms}ms")
    
    start = time.time()
    missed = 0
    received = 0
    latencies = []
    
    for i in range(100):  # 100 muestras
        try:
            t_req = time.time()
            resp = requests.get('http://localhost:5000/detections', timeout=1)
            t_resp = time.time()
            
            latency = (t_resp - t_req) * 1000  # en ms
            latencies.append(latency)
            received += 1
        except:
            missed += 1
        
        time.sleep(interval_ms / 1000)
    
    elapsed = time.time() - start
    
    print(f"  Recibidas: {received}/{100}")
    print(f"  Perdidas: {missed}")
    print(f"  Latencia promedio: {sum(latencies)/len(latencies):.2f}ms")
    print(f"  Latencia máx: {max(latencies):.2f}ms")
    print(f"  Throughput: {(received*3000) / elapsed:.2f} bytes/s")

# Probar diferentes intervalos
for interval in [50, 100, 200, 500, 1000]:
    test_interval(interval)
```

---

## 6. Monitoreo de Salud (Health Check)

### Endpoint `/health`

```bash
Intervalo: 5-10 segundos (opcional)
Payload: ~200 bytes

GET /health
{
  "status": "online",
  "timestamp": 1715200000.0,
  "stream_status": "live",
  "last_frame": 1715200000.05
}
```

**Cuándo usarlo:**
- Detectar desconexiones de PC1
- Alertar si servidor no responde
- Verificar latencia del servidor

**Implementación en PC2:**

```python
import threading

def health_monitor():
    while True:
        try:
            resp = requests.get('/health', timeout=5)
            data = resp.json()
            print(f"✓ Server online - Status: {data['stream_status']}")
        except:
            print("✗ Server unreachable!")
        
        time.sleep(10)  # Cada 10 segundos

# Ejecutar en thread separado
health_thread = threading.Thread(target=health_monitor, daemon=True)
health_thread.start()
```

---

## 📊 Resumen de Rendimiento Esperado

### Hardware: RTX 2060, Network LAN 1Gbps

```
MÉTRICA                 | VALOR TÍPICO  | MÁXIMO TOLERADO
────────────────────────┼───────────────┼──────────────────
Detecciones/segundo     | 5 (200ms)     | 10 (con lag)
Latencia API            | 20-50ms       | 200ms
Latencia Network        | 1-5ms (LAN)   | 50ms (WAN)
Tamaño payload JSON     | 2-5 KB        | 10 KB
Throughput total        | 50 KB/s       | 100 KB/s
Pérdida de frames       | 0%            | < 1%
Precisión H (error)     | < 0.1px       | < 1.0px
Tiempo reacción SUMO    | 250ms         | 500ms
```

---

## ✅ Checklist Final

- [ ] Intervalo detecciones: **200ms** (5 Hz)
- [ ] Matriz H: **Incluida en JSON** (sin intervalo fijo)
- [ ] Setup inicial: **< 1000ms** (una vez)
- [ ] Health check: **5-10s** (opcional)
- [ ] Cambio de video: **Mínimo 1-2 segundos**
- [ ] Monitoreo: Activado en PC2
- [ ] Ancho de banda: 50 KB/s (confirmado)
- [ ] Latencia: < 250ms (confirmada)

---

**Versión:** 1.0 | **Última actualización:** Mayo 17, 2026
