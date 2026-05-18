import cv2
import threading
import json
import time
import signal
from pathlib import Path
from collections import deque
from ultralytics import YOLO

from buffer_manager import buffer_manager
from calibration_manager import calibration_manager

VEHICLE_CLASSES = {
    'car': 2,
    'bus': 5,
    'truck': 7,
    'motorcycle': 3
}

VEHICLE_COLORS = {
    'car': (0, 165, 255),           # Naranja
    'bus': (0, 255, 0),             # Verde
    'truck': (0, 0, 255),           # Rojo
    'motorcycle': (255, 0, 0)     # Azul
}

detection_data = {
    'timestamp': None,
    'status_stream': 'offline',
    'counts': {k: 0 for k in VEHICLE_CLASSES.keys()},
    'total': 0,
    'density': 0.0,
    'congestion': 'LOW',
    'vehicles': []
}

data_lock = threading.Lock()
frame_lock = threading.Lock()
current_output_frame = None
fps_history = deque(maxlen=30)

# Variables de control para shutdown seguro
shutdown_event = threading.Event()
detector_thread_ref = None

# Variables de control para cambio de fuente de stream
stream_mode = 'fallback'  # Iniciar con video local, no intentar conexión al stream en vivo
stream_mode_lock = threading.Lock()
force_stream_restart = False

def get_stream_mode():
    """Obtener modo actual del stream (LIVE o FALLBACK)"""
    with stream_mode_lock:
        return stream_mode

def set_stream_mode(mode):
    """Cambiar modo del stream sin reiniciar el detector"""
    global stream_mode, force_stream_restart
    
    if mode not in ['live', 'fallback', 'respaldo1', 'respaldo2']:
        return False
    
    with stream_mode_lock:
        if stream_mode != mode:
            stream_mode = mode
            force_stream_restart = True
            print(f"[STREAM] Cambio de modo a {mode.upper()} solicitado")
            return True
    
    return True

def get_detection_data():
    with data_lock:
        # Copiar datos de detección
        data = json.loads(json.dumps(detection_data))
        
        # Agregar matriz de homografía si está disponible
        current_source = get_stream_mode()  # Usar función con lock
        H = calibration_manager.get_homography(current_source)
        
        if H is not None:
            data['homography_matrix'] = H.tolist()
        else:
            data['homography_matrix'] = None
        
        data['source'] = current_source
        
        # Agregar mapa actual (para que PC2 sepa cuál .net abrir)
        data['current_map'] = calibration_manager.current_map
        
        return data

def update_detection_data(new_data):
    global detection_data
    with data_lock:
        detection_data = new_data

def get_output_frame():
    with frame_lock:
        if current_output_frame is not None:
            return current_output_frame.copy()
        return None

def calculate_speed_px(prev_bbox, curr_bbox, fps=30):
    if not prev_bbox:
        return 0.0
    prev_center = ((prev_bbox[0] + prev_bbox[2]) / 2, (prev_bbox[1] + prev_bbox[3]) / 2)
    curr_center = ((curr_bbox[0] + curr_bbox[2]) / 2, (curr_bbox[1] + curr_bbox[3]) / 2)
    distance = ((curr_center[0] - prev_center[0])**2 + (curr_center[1] - prev_center[1])**2)**0.5
    return distance * fps

def determine_congestion(total_vehicles):
    density = min(1.0, total_vehicles / 20.0)
    
    # Niveles fijos según cantidad de vehículos
    if total_vehicles <= 3:
        congestion = 'LOW'
    elif total_vehicles <= 7:
        congestion = 'MEDIUM'
    elif total_vehicles <= 12:
        congestion = 'HIGH'
    else:
        congestion = 'CRITICAL'
        
    return congestion, density

def run_detector(stream_url='https://wzmedia.dot.ca.gov/D12/EB22BROOKHURST.stream/playlist.m3u8'):
    global current_output_frame, force_stream_restart, stream_mode

    # Permitir configurar el modelo por variable de entorno
    import os
    model_name = os.getenv('YOLO_MODEL', 'yolov8s.pt')  # Default: yolov8s (Small)
    model_path = Path(__file__).parent.parent / 'models' / model_name
    
    print(f"[YOLO] Cargando modelo: {model_name}")
    model = YOLO(str(model_path))
    model.to('cuda')
    print(f"[YOLO] ✓ Modelo cargado en GPU")

    respaldo_path = Path(__file__).parent.parent / 'videos' / 'respaldo.mp4'

    # Verificar que el archivo de respaldo existe
    if not respaldo_path.exists():
        print(f"⚠️  WARNING: Respaldo no encontrado: {respaldo_path}")
        print(f"   Por favor descarga el video con: ffmpeg -i '{stream_url}' -t 120 {respaldo_path}")

    cap = None
    stream_active = False
    fps = 16
    frame_width = 1280
    frame_height = 720

    def open_source(mode):
        """Abre la fuente de video según el modo"""
        nonlocal cap, stream_active, fps, frame_width, frame_height
        
        try:
            if mode == 'live':
                print(f"[LIVE] Intentando conectar al stream: {stream_url[:50]}...")
                cap_test = cv2.VideoCapture(stream_url)
                if cap_test.isOpened():
                    cap = cap_test
                    stream_active = True
                    print(f"[LIVE] ✅ Conexión al stream establecida")
                else:
                    cap_test.release()
                    print(f"[LIVE] ❌ No se pudo conectar. Usando video local...")
                    mode = 'fallback'
            
            if mode == 'respaldo1' or mode == 'respaldo2':
                video_path = Path(__file__).parent.parent / 'videos' / f'{mode}.mp4'
                if not video_path.exists():
                    # Intentar alternativa .MOV
                    video_path = Path(__file__).parent.parent / 'videos' / f'{mode}.MOV'
                
                if video_path.exists():
                    cap = cv2.VideoCapture(str(video_path))
                    stream_active = False
                    print(f"[{mode.upper()}] ✅ Video abierto: {video_path.name}")
                else:
                    print(f"[{mode.upper()}] ❌ No existe: {video_path}")
                    return False
            
            elif mode == 'fallback':
                if respaldo_path.exists():
                    cap = cv2.VideoCapture(str(respaldo_path))
                    stream_active = False
                    print(f"[FALLBACK] ✅ Video local abierto")
                else:
                    print(f"[FALLBACK] ❌ No existe: {respaldo_path}")
                    return False
            
            if cap is None or not cap.isOpened():
                return False
            
            # Obtener propiedades del video
            fps = cap.get(cv2.CAP_PROP_FPS) or 16
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
            
            return True
        
        except Exception as e:
            print(f"[ERROR] Al abrir fuente: {e}")
            return False

    # Inicializar según modo configurado
    current_stream_mode = get_stream_mode()
    if not open_source(current_stream_mode):
        # Si falla, intentar con el otro modo
        alt_mode = 'fallback' if current_stream_mode == 'live' else 'live'
        if not open_source(alt_mode):
            print("[ERROR] No se puede iniciar ninguna fuente de video")
            return

    print(f"[DETECTOR] Started | Video: {frame_width}x{frame_height} @ {fps:.1f}fps")

    # Calcular delay para throttle a 16 FPS máximo
    target_fps = 16
    frame_delay = 1.0 / max(target_fps, fps if stream_active else target_fps)
    last_frame_time = time.time()

    prev_bboxes = {}
    frame_count = 0
    start_time = time.time()

    try:
        while not shutdown_event.is_set():
            # Verificar si hay solicitud de cambio de stream
            with stream_mode_lock:
                if force_stream_restart:
                    force_stream_restart = False
                    new_mode = stream_mode
                    
                    print(f"[STREAM] Cerrando fuente actual...")
                    if cap is not None:
                        cap.release()
                        cap = None
                    
                    print(f"[STREAM] Abriendo nueva fuente: {new_mode.upper()}...")
                    if not open_source(new_mode):
                        print(f"[ERROR] No se pudo cambiar a {new_mode}")
                        # Intentar reconectar con modo alternativo
                        alt_mode = 'fallback' if new_mode == 'live' else 'live'
                        if not open_source(alt_mode):
                            print("[FATAL] No se puede abrir ninguna fuente")
                            break
                    # Recalcular frame_delay después de cambio de fuente
                    fps = cap.get(cv2.CAP_PROP_FPS) or 16
                    frame_delay = 1.0 / max(target_fps, fps if stream_active else target_fps)

            # Verificar que cap está inicializado
            if cap is None or not cap.isOpened():
                print("[WARN] VideoCapture no disponible, reiniciando...")
                time.sleep(0.5)
                continue

            ret, frame = cap.read()

            if not ret:
                if not stream_active:
                    # Video local: reiniciar desde el principio (bucle)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    print("[FALLBACK] Reiniciando video local desde el inicio")
                    continue
                else:
                    # Stream live: intentar reconectar
                    print("[LIVE] Stream interrumpido, reconectando...")
                    cap.release()
                    cap = None
                    time.sleep(2)
                    if not open_source('live'):
                        # Fallback a video local
                        if not open_source('fallback'):
                            print("[ERROR] No se pudo reconectar")
                            break
                    continue

            # THROTTLE: Sincronizar captura a 16 FPS máximo
            elapsed_since_last = time.time() - last_frame_time
            sleep_time = frame_delay - elapsed_since_last
            if sleep_time > 0:
                time.sleep(sleep_time)
            last_frame_time = time.time()

            frame_count += 1
            # Procesar todos los frames (no saltar 1 de cada 3 - ahora están a 16 FPS)
            if frame_count % 2 != 0:
                continue

            if frame is None:
                continue

            results = model.track(frame, persist=True, device='cuda', verbose=False)

            current_data = {
                'timestamp': time.time(),
                'status_stream': 'live' if stream_active else 'fallback loop',
                'counts': {k: 0 for k in VEHICLE_CLASSES.keys()},
                'total': 0,
                'density': 0.0,
                'congestion': 'LOW',
                'vehicles': []
            }

            annotated_frame = frame.copy()

            if results[0].boxes:
                for box in results[0].boxes:
                    class_id = int(box.cls)
                    class_name = results[0].names[class_id]

                    if class_name not in VEHICLE_CLASSES:
                        continue

                    track_id = int(box.id) if box.id else None
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    confidence = float(box.conf)

                    if track_id:
                        prev_bbox = prev_bboxes.get(track_id)
                        speed_px = calculate_speed_px(prev_bbox, (x1, y1, x2, y2), fps)
                        prev_bboxes[track_id] = (x1, y1, x2, y2)
                    else:
                        speed_px = 0.0

                    current_data['vehicles'].append({
                        'id': track_id,
                        'type': class_name,
                        'bbox': [x1, y1, x2, y2],
                        'speed_px': round(speed_px, 2),
                        'confidence': round(confidence, 3)
                    })
                    current_data['counts'][class_name] += 1

                    color = VEHICLE_COLORS.get(class_name, (0, 165, 255))
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                    label = f"#{track_id} {class_name} {round(speed_px, 1)}px/s"
                    cv2.putText(annotated_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            current_data['total'] = len(current_data['vehicles'])
            congestion, density = determine_congestion(current_data['total'])
            current_data['congestion'] = congestion
            current_data['density'] = round(density, 4)

            elapsed = time.time() - start_time
            real_fps = frame_count / max(elapsed, 0.001)
            fps_history.append(real_fps)
            avg_fps = sum(fps_history) / len(fps_history) if fps_history else 0

            cv2.putText(annotated_frame, f"Status: {current_data['status_stream'].upper()}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(annotated_frame, f"Total: {current_data['total']} | Congestion: {congestion}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(annotated_frame, f"FPS: {avg_fps:.1f}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 2)

            update_detection_data(current_data)

            with frame_lock:
                current_output_frame = annotated_frame

            buffer_manager.push(
                frame=annotated_frame,
                timestamp=current_data['timestamp'],
                metadata=current_data
            )

            if frame_count % 30 == 0:
                buffer_stats = buffer_manager.get_stats()
                print(f"[{current_data['status_stream'].upper()}] Vehicles: {current_data['total']} | "
                      f"Congestion: {congestion} | Density: {current_data['density']:.4f} | FPS: {avg_fps:.1f} | "
                      f"Buffer: {buffer_stats['current_frames']}/{buffer_stats['max_capacity']} frames ({buffer_stats['buffer_duration_seconds']:.1f}s)")

    except Exception as e:
        print(f"[ERROR] Detector exception: {e}")

    finally:
        print("[CLEANUP] Liberando recursos del detector...")
        if cap is not None:
            cap.release()
        print("[CLEANUP] VideoCapture cerrado")
        print("✅ Detector stopped.")

def start_detector_thread():
    global detector_thread_ref
    detector_thread_ref = threading.Thread(target=run_detector, daemon=False)
    detector_thread_ref.start()
    return detector_thread_ref

def signal_shutdown():
    """Señal segura de shutdown del detector"""
    print("\n[SIGNAL] Recibida señal de shutdown...")
    shutdown_event.set()

    # Esperar a que el detector termine (máximo 5 segundos)
    if detector_thread_ref:
        detector_thread_ref.join(timeout=5)
        print("[SIGNAL] Detector thread terminado")

def handle_sigint(signum, frame):
    """Manejador de CTRL+C"""
    print("\n" + "="*60)
    print("⚠️  CTRL+C detectado - Iniciando shutdown seguro...")
    print("="*60)
    signal_shutdown()
    print("\n✅ Todos los recursos liberados")
    print("👋 ¡Hasta luego!\n")
    exit(0)

def handle_sigterm(signum, frame):
    """Manejador de SIGTERM"""
    print("\n[SIGNAL] SIGTERM recibido")
    signal_shutdown()
    exit(0)
