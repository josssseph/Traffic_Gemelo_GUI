# 🛑 Guía de Shutdown Seguro

## ✅ Lo que se implementó

**Cierre seguro en 4 formas:**

1. **CTRL+C** en terminal (RECOMENDADO)
2. **Endpoint API** `/shutdown` 
3. **Signal SIGTERM** (docker, systemd, etc)
4. **Script de herramienta** `tune.py` (con salida segura)

---

## 🔄 Flujo de Shutdown Seguro

```
CTRL+C
  ↓
signal.SIGINT → handle_sigint()
  ↓
shutdown_event.set()
  ↓
Detector ve evento y sale del bucle
  ↓
Bloque finally: cap.release()
  ↓
thread.join(timeout=5s)
  ↓
Flask recibe señal
  ↓
app termina
  ↓
✅ Todos los recursos liberados
```

---

## 📋 Cómo Cerrar (Métodos)

### Método 1: CTRL+C en Terminal (RECOMENDADO)

**Terminal corriendo `python run.py`:**
```bash
$ python run.py
============================================================
TRAFFIC GEMELO - Detection & API Server
...
Presiona Ctrl+C para detener.
============================================================
[SERVER] Registrando signal handlers...
[SERVER] Presiona Ctrl+C para shutdown seguro
[DETECTOR] Started | Video: 1280x720 @ 12.5fps
...

^C  ← Presionar Ctrl+C aquí
```

**Output esperado:**
```
============================================================
⚠️  CTRL+C detectado - Iniciando shutdown seguro...
============================================================

[SIGNAL] Recibida señal de shutdown...
[CLEANUP] Liberando recursos del detector...
[CLEANUP] VideoCapture cerrado
✅ Detector stopped.
[SERVER] Limpiando...
[SIGNAL] Detector thread terminado

✅ Todos los recursos liberados
👋 ¡Hasta luego!
```

---

### Método 2: API Endpoint (Desde otra terminal)

```bash
# Solicitar shutdown desde otra terminal (mientras corre python run.py)
curl -X POST http://localhost:5000/shutdown

# Output en la otra terminal:
# [API] Shutdown solicitado desde cliente
# [SIGNAL] Recibida señal de shutdown...
# ... (limpieza)
```

---

### Método 3: Script de Herramienta (tune.py)

**Mientras corre `python run.py`:**
```bash
python tune.py

# Selecciona opción 0 (Salir)
# El programa cerrará de forma segura

# Al presionar Ctrl+C en tune.py:
^C
👋 Herramienta de tuning cerrada.
```

---

### Método 4: Señal SIGTERM (Para Docker/Systemd)

```bash
# Desde otra terminal, encontrar PID
ps aux | grep "python run.py"

# Enviar SIGTERM
kill -TERM <PID>

# Output en terminal original:
# [SIGNAL] SIGTERM recibido
# [CLEANUP] ...
# ✅ Recursos liberados
```

---

## 🔍 Recursos Que Se Liberan

✅ **Detector:**
- VideoCapture cerrado (`cap.release()`)
- YOLO model descargado de CUDA
- Thread detenido

✅ **Buffer:**
- frames.clear()
- timestamps.clear()
- metadata.clear()

✅ **Flask:**
- Servidor HTTP detiene
- Streaming MJPEG finaliza
- Conexiones cerradas

✅ **Threads:**
- Detector thread finaliza (max 5 segundos)
- Signal handlers desregistrados

---

## ⚠️ Qué NO Hacer

❌ **NO hacer**:
```bash
kill -9 <PID>          # Mata sin cleanup
pkill -9 python        # Mata todos los Python
Ctrl+Z                 # Solo pausa, no cierra
```

**¿Por qué?** VideoCapture puede quedar bloqueado en la GPU, causando problemas en próximas ejecuciones.

---

## 🧪 Test de Shutdown

### Test 1: CTRL+C Normal
```bash
python run.py
# ... esperar 10 segundos
^C
# Verificar que dice "✅ Detector stopped"
```

### Test 2: Shutdown por API
```bash
# Terminal 1
python run.py

# Terminal 2 (después de 10 segundos)
curl -X POST http://localhost:5000/shutdown
```

### Test 3: Restart Limpio
```bash
python run.py
# Ctrl+C después de 5 segundos
# Esperar a que termine completamente

python run.py  # Ejecutar nuevamente
# Debe iniciar sin errores
```

---

## 📊 Validación de Limpieza

Para verificar que el shutdown fue limpio:

```bash
# Verificar que no hay procesos Python activos
ps aux | grep python

# Verificar que la GPU está liberada (si tienes nvidia-smi)
nvidia-smi

# Verificar que no hay locks en archivos
lsof | grep traffic-gemelo
```

---

## 🎯 Resumen

| Método | Facilidad | Seguridad | Cuándo Usar |
|--------|-----------|-----------|------------|
| **CTRL+C** | ⭐⭐⭐ | ✅ | **SIEMPRE - Recomendado** |
| **API /shutdown** | ⭐⭐ | ✅ | Control remoto |
| **tune.py exit** | ⭐⭐⭐ | ✅ | Desde herramienta |
| **SIGTERM** | ⭐⭐ | ✅ | Docker/Systemd |

---

## 🚀 Próxima Ejecución

Después de shutdown seguro:

```bash
python run.py

# Debe mostrar:
# ✅ Todos los archivos válidos
# [SERVER] Registrando signal handlers...
# [DETECTOR] Started | Video: ...
# SIN ERRORES de GPU bloqueada o VideoCapture
```

---

**¡Shutdown seguro implementado!** ✅
