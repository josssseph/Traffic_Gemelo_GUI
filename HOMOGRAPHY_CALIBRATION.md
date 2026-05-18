# 📍 Sistema de Calibración de Homografía - Guía Completa

## Descripción General

El sistema de calibración permite mapear automáticamente puntos del video a coordenadas del mundo real (mapa SUMO). Esto es **crítico** para que PC2 (SUMO) inyecte vehículos en las posiciones correctas del mapa.

---

## 🏗️ Estructura de Directorios

```
~/traffic-gemelo/
├── videos/
│   ├── respaldo1.mp4      # Video local 1
│   └── respaldo2.MOV      # Video local 2
│
├── networks/
│   └── cuenca_respaldo1.net.xml   # Mapa SUMO correspondiente a respaldo1
│   # (En futuro: california.net.xml, cuenca_respaldo2.net.xml)
│
└── calibration/  (SE CREA AUTOMÁTICAMENTE)
    ├── live.pkl              # Matriz H para stream live (si se calibra)
    ├── live_metadata.json    # Metadata: puntos, errores, timestamp
    ├── respaldo1.pkl         # Matriz H para respaldo1.mp4
    ├── respaldo1_metadata.json
    ├── respaldo2.pkl
    ├── respaldo2_metadata.json
    └── ... (más si se agregan videos)
```

---

## 🎮 Cómo Usar la Pestaña de Calibración

### Paso 1: Acceder a la Interfaz

1. Ejecutar el servidor:
```bash
python run.py
```

2. Abrir navegador en `http://localhost:5000`

3. Hacer clic en pestaña **📍 Calibración Homografía**

### Paso 2: Seleccionar Fuente y Mapa

```
┌─ PANEL IZQUIERDO ──────────────────────┐
│ ⚙️ Configuración                        │
│                                         │
│ Selecciona Fuente de Video              │
│ [dropdown: live, respaldo1, respaldo2]  │
│                                         │
│ Selecciona Mapa (.net)                  │
│ [dropdown: cuenca_respaldo1, ...]       │
│                                         │
│ [Cargar Frame & Mapa]                   │
└─────────────────────────────────────────┘
```

**Importante:** Una vez seleccionados, los puntos previos se **limpian automáticamente**.

### Paso 3: Agregar Puntos de Calibración

```
┌─ PANEL DERECHO ────────────────────────┐
│ 📐 Mapeo de Puntos                      │
│                                         │
│ FRAME VIDEO    │    MAPA (.net)         │
│ [Canvas 1]     │    [Canvas 2]          │
│                │                        │
│ Clic en VIDEO  │    Clic en MAPA        │
│ (punto verde)  │    (punto naranja)     │
│                │                        │
│ Puntos: 1/4    │    Precisión: Baja    │
│                                         │
│ [Calcular Matriz H] [Reset Todo]        │
└─────────────────────────────────────────┘
```

**Flujo:**

1. **Clic en VIDEO** (canvas izquierdo) → aparece punto verde
2. **Clic en MAPA** (canvas derecho) → aparece punto naranja
3. Se conectan con línea invisible
4. Repetir para mínimo **4 puntos**
5. Automáticamente cuando hay 4+ puntos, botón se activa

### Paso 4: Calcular Matriz H

Cuando tengas 4+ puntos:

1. Haz clic en **[Calcular Matriz H]**
2. El sistema calcula la matriz automáticamente
3. Ver resultado:
   ```
   ✓ Homografía Calculada
   Mean Error: 0.0234
   Max Error: 0.1567
   ```

**Interpretación de errores:**
- `Mean Error < 0.1` → ✓ Excelente precisión
- `Mean Error 0.1-0.5` → ✓ Buena precisión
- `Mean Error > 0.5` → ⚠️ Calibración pobre, agregar más puntos

### Paso 5: Cambios Automáticos

**El sistema es inteligente:**
- Si cambias de VIDEO → se limpia calibración anterior
- Si cambias de MAPA → se limpia calibración anterior
- Si cambias de ambos → se limpia todo

**Si quieres REUTILIZAR calibración anterior:**
- Solo cambia MAPA (no VIDEO)
- O solo cambia VIDEO (no MAPA)

---

## 📊 Estructura del JSON de `/detections`

**ANTES** (sin homografía):
```json
{
  "timestamp": 1715200000.0,
  "status_stream": "live",
  "counts": {"car": 5, "bus": 1, "truck": 0, "motorcycle": 0},
  "total": 6,
  "density": 0.3,
  "congestion": "MEDIUM",
  "vehicles": [...]
}
```

**AHORA** (con homografía):
```json
{
  "timestamp": 1715200000.0,
  "status_stream": "live",
  "source": "respaldo1",
  "counts": {"car": 5, "bus": 1, "truck": 0, "motorcycle": 0},
  "total": 6,
  "density": 0.3,
  "congestion": "MEDIUM",
  "homography_matrix": [
    [0.00234, -0.00145, 125.5],
    [-0.00089, 0.00267, 342.2],
    [0.0, 0.0, 1.0]
  ],
  "vehicles": [
    {
      "id": 101,
      "type": "car",
      "bbox": [450, 250, 550, 350],
      "speed_px": 45.3,
      "confidence": 0.92
    },
    ...
  ]
}
```

**Campos nuevos:**
- `source` → "live", "respaldo1", "respaldo2", etc
- `homography_matrix` → matriz 3×3 para transformación píxel→mundo (o null si no calibrada)

---

## ⏱️ Intervalos de Envío Recomendados

### 1. **Detecciones de Vehículos**
```bash
Intervalo: 200ms (5 Hz)
Razón: Suficiente para tracking suave + evitar sobrecarga de red
Comando: Los logs muestran "[LIVE] Vehicles: 10 | FPS: 14-16"
```

### 2. **Matriz de Homografía**
```bash
Intervalo: SE ENVÍA UNA VEZ
Cuándo: 
  - Cuando se calibra (Click "Calcular Matriz H")
  - Se guarda a disco en calibration/
  - En todos los JSONs de `/detections` posteriores (hasta cambio de source)

Cambios:
  - Si cambias VIDEO → Se busca homografía anterior o null
  - Si cambias a nuevo LIVE → Se busca homografia_live.pkl
  - Si cambias a respaldo1 → Se busca homografia_respaldo1.pkl
```

### 3. **Buffer de Video**
```bash
Intervalo: 500ms (consultas desde PC2)
Razón: Balance entre latencia y uso de ancho de banda
Datos: 5 segundos × 16 FPS = 80 frames (circular)
```

### 4. **Consultas de Configuración**
```bash
Intervalo: Una sola vez al iniciar PC2
Endpoints:
  GET /calibration/sources      → Lista disponible
  GET /calibration/maps         → Lista disponible
  GET /calibration/status       → Ver si están calibradas
```

---

## 🔄 Flujo Completo: Video→Mapa

```
USUARIO EN PC1:
  1. Selecciona "respaldo1" en dropdown video
     └─ Sistema carga: videos/respaldo1.mp4

  2. Selecciona "cuenca_respaldo1" en dropdown mapa
     └─ Sistema carga: networks/cuenca_respaldo1.net.xml

  3. Clic [Cargar Frame & Mapa]
     └─ Canvas izquierdo: Frame del video
     └─ Canvas derecho: Mapa (XML renderizado)

  4. Mapea 4+ puntos
     └─ Clic en intersección en VIDEO (px: 450, 250)
     └─ Clic en misma intersección en MAPA (m: 125.5, 342.2)
     └─ REPETIR 3 veces más

  5. Clic [Calcular Matriz H]
     └─ Se guarda:
        - calibration/respaldo1.pkl (matriz H)
        - calibration/respaldo1_metadata.json (detalles)

SERVIDOR EN PC1:
  6. GET /detections devuelve:
     {
       "source": "respaldo1",
       "homography_matrix": [[...], [...], [...]],
       "vehicles": [...]
     }

PC2 (SUMO) lee JSON:
  7. Extrae homography_matrix
  8. Extrae vehicles
  9. Para cada vehículo:
       x_px, y_px = bbox del vehículo
       x_mundo, y_mundo = H @ (x_px, y_px)
       → inyecta en SUMO con coordenadas correctas
```

---

## 🛠️ Endpoints de Calibración

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/calibration/sources` | Lista videos disponibles |
| GET | `/calibration/maps` | Lista mapas (.net) disponibles |
| GET | `/calibration/frame/<source>` | Obtiene frame de video (base64) |
| GET | `/calibration/map-preview/<map>` | Obtiene contenido XML del mapa |
| POST | `/calibration/set-context` | Establece video + mapa actual |
| POST | `/calibration/add-point` | Agrega un punto de calibración |
| GET | `/calibration/status` | Ve estado actual (puntos, precisión) |
| POST | `/calibration/calculate` | Calcula matriz H con puntos actuales |
| POST | `/calibration/clear` | Limpia puntos actuales |

---

## 📋 Checklist de Configuración

### Preparación Inicial

- [ ] `videos/respaldo1.mp4` existe
- [ ] `videos/respaldo2.MOV` existe  
- [ ] `networks/cuenca_respaldo1.net.xml` existe
- [ ] Ejecutar `python run.py` sin errores
- [ ] Acceder a `http://localhost:5000` ✓

### Primer Mapeo (respaldo1)

- [ ] Seleccionar "respaldo1" en dropdown video
- [ ] Seleccionar "cuenca_respaldo1" en dropdown mapa
- [ ] Clic [Cargar Frame & Mapa]
- [ ] Mapear 4 puntos característicos (esquinas de intersección, árboles, señales)
- [ ] Clic [Calcular Matriz H]
- [ ] Ver `Mean Error < 0.2` ✓
- [ ] Archivo `calibration/respaldo1.pkl` creado
- [ ] Archivo `calibration/respaldo1_metadata.json` creado

### Segundo Mapeo (respaldo2)

- [ ] Crear `networks/cuenca_respaldo2.net.xml` (si aún no existe)
- [ ] Seleccionar "respaldo2" en dropdown video
- [ ] Seleccionar "cuenca_respaldo2" en dropdown mapa
- [ ] Repetir proceso de mapeo
- [ ] Verificar archivos generados

### Validación Final

- [ ] GET `http://localhost:5000/detections` incluye `homography_matrix`
- [ ] GET `http://localhost:5000/detections` incluye `source`
- [ ] PC2 puede descargar JSON y extraer matriz H

---

## 🚨 Troubleshooting

### "No aparecen los videos en dropdown"
```
Solución:
1. Verificar que videos están en ~/traffic-gemelo/videos/
2. Verificar extensiones (.mp4, .MOV, .avi, .mkv, .webm)
3. Reiniciar servidor (Ctrl+C y python run.py)
4. Ver consola para mensajes: [VIDEO] Fuentes detectadas: ...
```

### "No aparecen los mapas en dropdown"
```
Solución:
1. Verificar que .net están en ~/traffic-gemelo/networks/
2. Verificar nombres: cuenca_respaldo1.net.xml (sin caracteres especiales)
3. Reiniciar servidor
4. Ver consola: [VIDEO] Redes detectadas: ...
```

### "Error calculando matriz H"
```
Solución:
1. Agregar más puntos (4 mínimo, 8+ ideal)
2. Seleccionar puntos que NO sean colineales (no en línea recta)
3. Distribuir puntos en toda el área (no todos en una esquina)
4. Ver `Mean Error`: si es > 1.0, recalibrar con mejores puntos
```

### "Mean Error muy alto (> 0.5)"
```
Solución:
1. Limpiar puntos [Limpiar Puntos]
2. Seleccionar puntos más precisos (usar intersecciones claras)
3. Verificar que los puntos en MAPA corresponden exactamente al VIDEO
4. Agregar 2-3 puntos más para mayor precisión
```

### "Homografía no se guarda"
```
Solución:
1. Verificar permisos: ls -l calibration/
2. Crear manualmente si no existe: mkdir -p calibration
3. Ver errores en consola: [CALIB] Error saving H: ...
```

---

## 📈 Próximas Mejoras

- [ ] Visualización 3D del mapa dentro de la UI
- [ ] Validación automática de puntos (evitar colineales)
- [ ] Sugerencias automáticas de puntos (detectar esquinas)
- [ ] Exportar/Importar calibraciones
- [ ] Modo batch: calibrar múltiples videos de una vez
- [ ] Estadísticas: histórico de calibraciones

---

**Versión:** 1.0 | **Última actualización:** Mayo 17, 2026
