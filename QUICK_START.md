# ⚡ QUICK START - Calibración Homografía en 5 Minutos

## 1️⃣ Verificar que Todo Está en Lugar

```bash
cd ~/traffic-gemelo

# Verificar estructura
ls videos/
# Output debe mostrar: respaldo1.mp4, respaldo2.MOV

ls networks/
# Output debe mostrar: cuenca_respaldo1.net.xml

ls src/
# Output debe mostrar: calibration_manager.py, video_manager.py
```

## 2️⃣ Iniciar el Servidor

```bash
# Terminal 1
source venv/bin/activate
python run.py

# Output esperado:
# [SERVER] Starting Flask on 0.0.0.0:5000
# [VIDEO] Fuentes detectadas: ['live', 'respaldo1', 'respaldo2']
# [VIDEO] Redes detectadas: ['cuenca_respaldo1']
```

## 3️⃣ Abrir Dashboard

```bash
# Navegador
http://localhost:5000

# Deberías ver:
# - Pestaña 1: "📊 Dashboard" (activa)
# - Pestaña 2: "📍 Calibración Homografía"
```

## 4️⃣ Calibrar el Video (2 minutos)

1. **Clic en pestaña "📍 Calibración Homografía"**

2. **Selecciona fuente y mapa:**
   ```
   Fuente: respaldo1
   Mapa: cuenca_respaldo1
   ```

3. **Clic en [Cargar Frame & Mapa]**
   - Izquierda: Verás frame del video
   - Derecha: Verás canvas del mapa

4. **Mapea 4 puntos:**
   
   **Punto 1:**
   - Clic en VIDEO (ej: esquina de intersección) → **VERDE**
   - Clic en MAPA (misma ubicación) → **NARANJA**
   
   **Punto 2-4:** Repite el proceso
   
   💡 **Tip:** Usa puntos característicos:
   - Esquinas de intersecciones
   - Árboles
   - Señales de tránsito
   - Cambios de calles

5. **Clic en [Calcular Matriz H]**
   - Esperarás 1-2 segundos
   - Verás: ✓ Homografía Calculada
   - Errores mostrados (target: < 0.1)

6. **¡Listo!** Archivo guardado:
   ```
   calibration/respaldo1.pkl
   calibration/respaldo1_metadata.json
   ```

## 5️⃣ Validar que Funciona

```bash
# Terminal 2
curl http://localhost:5000/detections | jq .

# Debes ver:
{
  "source": "respaldo1",
  "homography_matrix": [
    [0.00234, -0.00145, 125.5],
    ...
  ],
  "vehicles": [...]
}
```

---

## ✅ ¡Listo!

Tu calibración está completa. Ahora PC2 (SUMO) puede:

```bash
# PC2 (Dev B)
1. Descargar archivo: calibration/respaldo1.pkl
2. Leer homography_matrix del JSON
3. Transformar píxeles → coordenadas mundo
4. Inyectar vehículos en SUMO con posiciones correctas
```

---

## 📸 Interfaz Visual (ASCII)

```
┌────────────────────────────────────────────────────────┐
│ 📍 CALIBRACIÓN HOMOGRAFÍA                              │
├────────────────┬────────────────────────────────────────┤
│  ⚙️ CONFIG     │         📐 MAPEO DE PUNTOS             │
│                │                                         │
│ [respaldo1 ▼] │  ┌───────────┬──────────────┐           │
│ [cuenca... ▼]  │  │ FRAME     │ MAPA         │           │
│                │  │ VIDEO     │ (cuenca...)  │           │
│ [Cargar]       │  │           │              │           │
│ [Limpiar]      │  │  • (1)    │  ● (1)       │           │
│                │  │ (450,250) │ (125.5, 342) │           │
│ Puntos: 4/4 ✓  │  │           │              │           │
│ Precisión: ⭐  │  │  • (2)    │  ● (2)       │           │
│                │  │  • (3)    │  ● (3)       │           │
│ ✓ Calibrado    │  │  • (4)    │  ● (4)       │           │
│ Error: 0.045   │  │           │              │           │
│                │  └───────────┴──────────────┘           │
│                │                                         │
│                │ [Calcular H] [Reset]                   │
│                │                                         │
│                │ ✓ Homografía Calculada                 │
│                │ Mean Error: 0.0234                      │
│                │ Max Error: 0.1567                       │
└────────────────┴────────────────────────────────────────┘
```

---

## 🔥 Si Algo Falla

### Error: "No aparecen videos"
```bash
ls -la videos/
# Debe mostrar: respaldo1.mp4, respaldo2.MOV
# Si falta, copiar archivo
```

### Error: "No aparecen mapas"
```bash
ls -la networks/
# Debe mostrar: cuenca_respaldo1.net.xml
# Si falta, crear o copiar
```

### Error: "Matrix H no se guarda"
```bash
mkdir -p calibration
chmod 755 calibration
# Reiniciar servidor
```

### Error: "Mean Error muy alto (> 0.5)"
```
1. Limpiar puntos [Limpiar Puntos]
2. Seleccionar puntos mejores (más específicos)
3. Intentar de nuevo
4. O agregar más puntos (8+ para mayor precisión)
```

---

## 📱 Una Vez Calibrado...

```
✅ PC1 (Tu PC)
   └─ /detections incluye matriz H
   └─ Listo para conectarse a SUMO

✅ Dev B (PC2 - SUMO)
   └─ Descarga calibration/respaldo1.pkl
   └─ Lee homography_matrix del JSON
   └─ Transforma pixels → mundo
   └─ Inyecta en SUMO

✅ Dev C (PC3 - Dashboard)
   └─ Visualiza vehículos en tiempo real
   └─ Muestra congestión
   └─ Integra con SUMO
```

---

**Time: 5 minutos ⏱️ | Complejidad: 🟢 Fácil**
