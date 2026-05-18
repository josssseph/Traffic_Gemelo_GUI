from flask import Flask, jsonify, Response, render_template_string, request
from flask_cors import CORS
import cv2
import sys
import time
import signal
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from detector import (get_detection_data, get_output_frame, start_detector_thread,
                      signal_shutdown, handle_sigint, handle_sigterm,
                      get_stream_mode, set_stream_mode)
from buffer_manager import buffer_manager
from video_codecs import create_codec, get_active_codec, switch_codec, CODEC_CONFIG
from calibration_manager import calibration_manager
from video_manager import video_manager

app = Flask(__name__)
CORS(app)

detector_thread = None
last_frame_time = 0

def generate_frames():
    """
    Streaming real-time OPTIMIZADO - Sin buffer congestionado
    Lee SOLO el frame más reciente y lo codifica
    """
    consecutive_errors = 0
    max_errors = 30

    while True:
        try:
            # Obtener SOLO el frame más reciente (no histórico)
            frame, timestamp, metadata = buffer_manager.get_latest()

            if frame is None:
                time.sleep(0.05)
                continue

            consecutive_errors = 0

            # Codificar con codec activo
            codec = get_active_codec()
            frame_bytes = codec.encode(frame)

            if frame_bytes is None:
                time.sleep(0.05)
                continue

            # Enviar como MJPEG
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
                   + frame_bytes + b'\r\n')

            global last_frame_time
            last_frame_time = time.time()

            # Control de FPS: Sincronizar a 16 FPS (real-time)
            time.sleep(1.0 / 16)

        except GeneratorExit:
            print("[INFO] Streaming detenido por cliente")
            break

        except Exception as e:
            print(f"[ERROR] MJPEG generator: {e}")
            consecutive_errors += 1

            if consecutive_errors >= max_errors:
                print("[ERROR] Demasiados errores en stream, cerrando...")
                break

            time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    """Stream MJPEG del video anotado en tiempo real"""
    try:
        return Response(generate_frames(),
                       mimetype='multipart/x-mixed-replace; boundary=frame',
                       headers={'Cache-Control': 'no-cache, no-store, must-revalidate'})
    except Exception as e:
        print(f"[ERROR] Video feed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/detections', methods=['GET'])
def detections():
    """API JSON con detecciones actuales"""
    try:
        data = get_detection_data()
        return jsonify(data), 200
    except Exception as e:
        print(f"[ERROR] Detections endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check del servidor"""
    try:
        current_data = get_detection_data()
        return jsonify({
            'status': 'online',
            'timestamp': current_data.get('timestamp'),
            'stream_status': current_data.get('status_stream'),
            'last_frame': last_frame_time
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/codec/config', methods=['GET'])
def get_codec_config():
    """Obtener configuración actual del codec"""
    try:
        codec = get_active_codec()
        return jsonify({
            'current_codec': CODEC_CONFIG['active_codec'],
            'quality': CODEC_CONFIG['quality'],
            'preprocessing': CODEC_CONFIG['preprocessing'],
            'target_fps': CODEC_CONFIG['target_fps'],
            'resize_factor': CODEC_CONFIG['resize_factor'],
            'codec_stats': codec.get_stats(),
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/codec/switch/<codec_type>/<int:quality>', methods=['POST'])
def switch_codec_endpoint(codec_type, quality):
    """
    Cambiar codec en tiempo real

    Args:
        codec_type: 'jpeg', 'webp', 'h264', 'adaptive'
        quality: 1-100
    """
    try:
        quality = max(1, min(100, quality))
        switch_codec(codec_type.lower(), quality=quality)

        return jsonify({
            'success': True,
            'codec': CODEC_CONFIG['active_codec'],
            'quality': CODEC_CONFIG['quality'],
            'message': f"Codec cambiado a {codec_type} con calidad {quality}"
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/preprocessing/switch/<preset>', methods=['POST'])
def switch_preprocessing_endpoint(preset):
    """
    Cambiar preprocessing en tiempo real
    
    Args:
        preset: 'quality', 'balanced', 'fast', 'none'
    """
    try:
        valid_presets = ['quality', 'balanced', 'fast', 'none']
        if preset.lower() not in valid_presets:
            return jsonify({'error': f'Preset debe ser uno de: {", ".join(valid_presets)}'}), 400
        
        CODEC_CONFIG['preprocessing'] = preset.lower()
        # Recrear codec activo con nuevo preprocessing
        switch_codec(CODEC_CONFIG['active_codec'], quality=CODEC_CONFIG['quality'])
        
        return jsonify({
            'success': True,
            'preprocessing': CODEC_CONFIG['preprocessing'],
            'message': f"Preprocessing cambiado a {preset}"
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/buffer/stats', methods=['GET'])
def get_buffer_stats():
    """Obtener estadísticas del buffer de 15s"""
    try:
        stats = buffer_manager.get_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stream/status', methods=['GET'])
def get_stream_status():
    """Obtener estado actual del stream (LIVE o FALLBACK)"""
    try:
        current_data = get_detection_data()
        return jsonify({
            'current_mode': get_stream_mode(),
            'status_stream': current_data.get('status_stream'),
            'available_modes': ['live', 'fallback']
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stream/switch/<mode>', methods=['POST'])
def switch_stream_mode(mode):
    """
    Cambiar entre stream LIVE y FALLBACK sin reinicio
    
    Args:
        mode: 'live' o 'fallback'
    """
    try:
        if mode.lower() not in ['live', 'fallback']:
            return jsonify({'error': 'Modo debe ser "live" o "fallback"'}), 400
        
        success = set_stream_mode(mode.lower())
        
        if success:
            return jsonify({
                'success': True,
                'new_mode': mode.lower(),
                'message': f"Stream cambiado a {mode.upper()}"
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo cambiar el modo del stream'
            }), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== CALIBRACIÓN HOMOGRAFÍA ====================

@app.route('/calibration/sources', methods=['GET'])
def get_calibration_sources():
    """Obtiene lista de fuentes de video disponibles"""
    try:
        sources = video_manager.get_available_sources()
        calibration_status = calibration_manager.get_homography_list()
        
        # Enriquecer con status de calibración
        for name in sources:
            sources[name]['calibrated'] = name in calibration_status
            if name in calibration_status:
                sources[name]['calibration_meta'] = calibration_status[name]
        
        return jsonify({
            'success': True,
            'sources': sources,
            'current_source': get_stream_mode()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/maps', methods=['GET'])
def get_calibration_maps():
    """Obtiene lista de mapas .net disponibles"""
    try:
        maps = video_manager.get_available_maps()
        return jsonify({
            'success': True,
            'maps': maps,
            'count': len(maps)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/frame/<source>', methods=['GET'])
def get_calibration_frame(source):
    """
    Obtiene frame actual de una fuente en base64
    
    Args:
        source: 'live', 'respaldo1', 'respaldo2'
    """
    try:
        frame_base64 = video_manager.get_frame_from_source(source)
        
        if frame_base64 is None:
            return jsonify({'error': f'No se pudo obtener frame de {source}'}), 404
        
        return jsonify({
            'success': True,
            'source': source,
            'frame': frame_base64,
            'resolution': video_manager.get_frame_resolution(source)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/map-preview/<map_name>', methods=['GET'])
def get_map_preview(map_name):
    """
    Obtiene visualización SVG del mapa (.net)
    
    Args:
        map_name: 'cuenca_respaldo1', etc
    """
    try:
        map_svg = video_manager.get_map_as_svg(map_name)
        
        if map_svg is None:
            return jsonify({'error': f'Map not found: {map_name}'}), 404
        
        return jsonify({
            'success': True,
            'map_name': map_name,
            'svg': map_svg
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/set-context', methods=['POST'])
def set_calibration_context():
    """
    Establece la fuente de video y mapa para calibración
    Limpia puntos anteriores si cambió de contexto
    TAMBIEN cambia el stream_mode del detector a la fuente seleccionada
    
    Body:
        {
            "source": "respaldo1" | "respaldo2" | "live",
            "map": "cuenca_respaldo1"
        }
    """
    try:
        data = request.json
        source = data.get('source')
        map_name = data.get('map')
        
        if not source or not map_name:
            return jsonify({'error': 'source y map son requeridos'}), 400
        
        changed = calibration_manager.set_calibration_context(source, map_name)
        
        # IMPORTANTE: Cambiar el stream_mode del detector a la fuente seleccionada
        set_stream_mode(source)
        
        return jsonify({
            'success': True,
            'changed': changed,
            'source': source,
            'map': map_name,
            'message': 'Contexto establecido, puntos previos limpiados' if changed else 'Mismo contexto'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/add-point', methods=['POST'])
def add_calibration_point():
    """
    Agrega un punto de calibración
    
    Body:
        {
            "point_px": [x, y],      # píxeles del video
            "point_world": [x, y]    # coordenadas del mapa
        }
    """
    try:
        data = request.json
        point_px = tuple(data.get('point_px'))
        point_world = tuple(data.get('point_world'))
        
        result = calibration_manager.add_point(point_px, point_world)
        
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/status', methods=['GET'])
def get_calibration_status():
    """Obtiene estado actual de calibración"""
    try:
        state = calibration_manager.get_current_state()
        homographies = calibration_manager.get_homography_list()
        
        return jsonify({
            'success': True,
            'current_state': state,
            'calibrations': homographies
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/clear', methods=['POST'])
def clear_calibration_points():
    """Limpia los puntos actuales de calibración"""
    try:
        calibration_manager.clear_current_points()
        
        return jsonify({
            'success': True,
            'message': 'Puntos limpiados'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/calculate', methods=['POST'])
def calculate_homography():
    """Calcula matriz H basada en puntos actuales"""
    try:
        result = calibration_manager.calculate_homography()
        
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calibration/inspect/<source>', methods=['GET'])
def inspect_homography(source):
    """
    Inspecciona y valida matriz de homografía
    Devuelve análisis detallado de escala, puntos, y anomalías
    """
    try:
        import numpy as np
        
        # Obtener metadata
        metadata = calibration_manager.metadata.get(source)
        if not metadata:
            return jsonify({'error': f'No calibration found for {source}'}), 404
        
        H = calibration_manager.get_homography(source)
        if H is None:
            return jsonify({'error': f'Failed to load matrix for {source}'}), 404
        
        points_video = np.array(metadata['points']['video'], dtype=np.float32)
        points_world = np.array(metadata['points']['world'], dtype=np.float32)
        
        # Análisis de escalas
        video_x_range = float(points_video[:, 0].max() - points_video[:, 0].min())
        video_y_range = float(points_video[:, 1].max() - points_video[:, 1].min())
        world_x_range = float(points_world[:, 0].max() - points_world[:, 0].min())
        world_y_range = float(points_world[:, 1].max() - points_world[:, 1].min())
        
        scale_x = float(video_x_range / world_x_range) if world_x_range > 0 else 0
        scale_y = float(video_y_range / world_y_range) if world_y_range > 0 else 0
        scale_ratio = float(scale_x / scale_y) if scale_y > 0 else 0
        
        # Detectar anomalías
        anomalies = []
        if abs(scale_ratio - 1.0) > 0.5:
            anomalies.append({
                'type': 'scale_mismatch',
                'severity': 'WARNING',
                'message': f'Scale X/Y ratio is {scale_ratio:.2f} (should be ~1.0). '
                          f'This could cause movement distortion. Check calibration points.',
                'scale_x_px_per_m': float(scale_x),
                'scale_y_px_per_m': float(scale_y),
                'ratio': float(scale_ratio)
            })
        
        # Validar reprojección
        reprojected = cv2.perspectiveTransform(
            points_video.reshape(-1, 1, 2), H
        ).reshape(-1, 2)
        errors = np.linalg.norm(reprojected - points_world, axis=1)
        
        if np.max(errors) > 2.0:
            anomalies.append({
                'type': 'high_reprojection_error',
                'severity': 'WARNING',
                'message': 'High reprojection error. Calibration points may be inaccurate.',
                'max_error': float(np.max(errors)),
                'mean_error': float(np.mean(errors))
            })
        
        return jsonify({
            'success': True,
            'source': source,
            'calibration_points': {
                'count': int(len(points_video)),
                'video_points': points_video.tolist(),
                'world_points': points_world.tolist(),
                'reprojection_errors': errors.tolist()
            },
            'matrix': {
                'H': H.tolist(),
                'shape': [3, 3]
            },
            'scales': {
                'pixels_per_meter_x': float(scale_x),
                'pixels_per_meter_y': float(scale_y),
                'ratio_x_to_y': float(scale_ratio),
                'interpretation': f'{scale_x:.2f} px/m horizontal, {scale_y:.2f} px/m vertical'
            },
            'errors': {
                'mean_reprojection': float(metadata['mean_error']),
                'max_reprojection': float(metadata['max_error']),
                'per_point': errors.tolist()
            },
            'metadata': metadata,
            'anomalies': anomalies,
            'coordinate_system': {
                'video': 'pixel (0,0 = top-left)',
                'world': 'SUMO world coords (X=east-west, Y=north-south from junction center)',
                'note': 'Y axis in SUMO may be inverted compared to pixel coordinates'
            }
        }), 200
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

# ==================== FIN CALIBRACIÓN ====================

@app.route('/shutdown', methods=['POST'])
def shutdown_server():
    """Endpoint para shutdown seguro del servidor"""
    try:
        print("\n[API] Shutdown solicitado desde cliente")
        response = jsonify({
            'status': 'shutting_down',
            'message': 'Servidor cerrando de forma segura...'
        })

        def do_shutdown():
            time.sleep(1)
            signal_shutdown()
            sys.exit(0)

        shutdown_thread = threading.Thread(target=do_shutdown, daemon=False)
        shutdown_thread.start()

        return response, 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    """Pantalla de calibración obligatoria - Seleccionar fuente, calibrar puntos, calcular matriz H"""
    html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Gemelo Digital - Calibración</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #fff;
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1600px; margin: 0 auto; }
            h1 { color: #00a5ff; margin-bottom: 20px; }
            .step-section {
                background: rgba(0, 20, 40, 0.9);
                border: 2px solid #00a5ff;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
            }
            .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
            label { font-size: 0.95em; display: block; margin-bottom: 8px; font-weight: bold; color: #aaa; }
            select {
                width: 100%;
                padding: 12px;
                background: rgba(0, 165, 255, 0.1);
                border: 1px solid #00a5ff;
                color: #fff;
                border-radius: 6px;
                font-size: 1em;
                cursor: pointer;
            }
            .calibration-workspace {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-top: 20px;
            }
            .canvas-section, .map-section {
                background: rgba(0, 50, 100, 0.5);
                border: 2px solid #00a5ff;
                border-radius: 8px;
                padding: 15px;
            }
            .section-title { color: #00a5ff; font-weight: bold; margin-bottom: 10px; }
            canvas {
                width: 100%;
                height: 400px;
                background: #000;
                border-radius: 6px;
                cursor: crosshair;
            }
            #map-container {
                width: 100%;
                height: 400px;
                background: #000;
                border-radius: 6px;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
            }
            #map-container svg {
                width: 100%;
                height: 100%;
                cursor: crosshair;
            }
            .points-list {
                background: #000;
                border: 1px solid #333;
                padding: 10px;
                border-radius: 4px;
                max-height: 150px;
                overflow-y: auto;
                font-family: monospace;
                font-size: 0.75em;
                margin-top: 10px;
            }
            .point-item { color: #00ff88; padding: 5px; border-bottom: 1px solid #333; }
            .button-group {
                display: flex;
                gap: 10px;
                margin-top: 15px;
                flex-wrap: wrap;
            }
            button {
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                transition: all 0.3s;
            }
            .btn-primary {
                background: #00a5ff;
                color: #000;
            }
            .btn-primary:hover { background: #0088cc; }
            .btn-primary:disabled { background: #666; cursor: not-allowed; }
            .btn-secondary {
                background: rgba(0, 165, 255, 0.2);
                color: #00a5ff;
                border: 1px solid #00a5ff;
            }
            .btn-secondary:hover { background: rgba(0, 165, 255, 0.3); }
            .btn-danger {
                background: #ff6600;
                color: #fff;
            }
            .btn-danger:hover { background: #ff8822; }
            .status { color: #aaa; font-size: 0.9em; margin-top: 10px; }
            .status.success { color: #00ff88; }
            .status.error { color: #ff6666; }
            .hidden { display: none !important; }
            @media (max-width: 1200px) {
                .calibration-workspace { grid-template-columns: 1fr; }
                canvas, #map-container { height: 300px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎥 Configuración Inicial - Calibración de Matriz Homográfica</h1>
            
            <!-- PASO 1: Seleccionar Fuente y Mapa -->
            <div class="step-section">
                <h2>Paso 1: Selecciona Fuente y Mapa</h2>
                <div class="grid-2">
                    <div>
                        <label for="source-select">📹 Fuente de Video</label>
                        <select id="source-select">
                            <option value="">-- Selecciona fuente --</option>
                        </select>
                    </div>
                    <div>
                        <label for="map-select">🗺️ Mapa (Red SUMO)</label>
                        <select id="map-select">
                            <option value="">-- Selecciona mapa --</option>
                        </select>
                    </div>
                </div>
                <div class="status" id="step1-status"></div>
            </div>
            
            <!-- PASO 2: Calibración -->
            <div class="step-section hidden" id="calibration-section">
                <h2>Paso 2: Calibración - Mapeo Píxeles a Metros</h2>
                <p style="color: #aaa; margin-bottom: 15px;">
                    Haz clic en el video para marcar puntos (píxeles). 
                    Luego haz clic en el mapa para indicar las coordenadas reales (metros).
                    Necesitas mínimo 4 puntos para calcular la matriz.
                </p>
                
                <div class="calibration-workspace">
                    <div class="canvas-section">
                        <div class="section-title">📷 Video Frame</div>
                        <canvas id="video-canvas"></canvas>
                        <div class="points-list" id="pixels-list">
                            <strong style="color: #00a5ff;">Puntos píxeles:</strong>
                        </div>
                    </div>
                    
                    <div class="map-section">
                        <div class="section-title">🗺️ Mapa Interactivo</div>
                        <div id="map-container"></div>
                        <div class="points-list" id="world-list">
                            <strong style="color: #00a5ff;">Puntos mundo:</strong>
                        </div>
                    </div>
                </div>
                
                <div class="button-group">
                    <button class="btn-primary" id="calc-btn" disabled>✓ Calcular Matriz H</button>
                    <button class="btn-secondary" id="clear-btn">🔄 Limpiar Puntos</button>
                    <button class="btn-secondary" id="back-btn">← Atrás</button>
                </div>
                <div class="status" id="step2-status"></div>
            </div>
            
            <!-- PASO 3: Dashboard -->
            <div class="step-section hidden" id="success-section">
                <h2>✓ Calibración Completa</h2>
                <p style="color: #aaa; margin-bottom: 15px;">
                    La matriz de homografía ha sido calculada exitosamente.
                    Ya puedes ir al dashboard para ver el video en tiempo real.
                </p>
                <button class="btn-primary" onclick="window.location.href='/dashboard';">
                    → Ir a Dashboard
                </button>
            </div>
        </div>
        
        <script>
            const sourceSelect = document.getElementById('source-select');
            const mapSelect = document.getElementById('map-select');
            const calibrationSection = document.getElementById('calibration-section');
            const successSection = document.getElementById('success-section');
            const canvas = document.getElementById('video-canvas');
            const ctx = canvas.getContext('2d');
            const mapContainer = document.getElementById('map-container');
            const pixelsList = document.getElementById('pixels-list');
            const worldList = document.getElementById('world-list');
            const calcBtn = document.getElementById('calc-btn');
            const clearBtn = document.getElementById('clear-btn');
            const backBtn = document.getElementById('back-btn');
            const step1Status = document.getElementById('step1-status');
            const step2Status = document.getElementById('step2-status');
            
            let frameImage = null;
            let mapSvg = null;
            let pixelPoints = [];
            let worldPoints = [];
            let clickMode = 'pixel';
            
            async function loadOptions() {
                try {
                    const [sourcesResp, mapsResp] = await Promise.all([
                        fetch('/calibration/sources'),
                        fetch('/calibration/maps')
                    ]);
                    const sources = await sourcesResp.json();
                    const maps = await mapsResp.json();
                    
                    sourceSelect.innerHTML = '<option value="">-- Selecciona fuente --</option>';
                    for (const [name, info] of Object.entries(sources.sources)) {
                        sourceSelect.innerHTML += `<option value="${name}">${name}</option>`;
                    }
                    
                    mapSelect.innerHTML = '<option value="">-- Selecciona mapa --</option>';
                    for (const [name] of Object.entries(maps.maps)) {
                        mapSelect.innerHTML += `<option value="${name}">${name}</option>`;
                    }
                } catch (err) {
                    step1Status.textContent = '❌ Error cargando opciones';
                    step1Status.classList.add('error');
                }
            }
            
            async function loadCalibrationData() {
                const source = sourceSelect.value;
                const map = mapSelect.value;
                
                if (!source || !map) {
                    calibrationSection.classList.add('hidden');
                    successSection.classList.add('hidden');
                    step1Status.textContent = '❌ Selecciona fuente y mapa';
                    return;
                }
                
                try {
                    const frameResp = await fetch(`/calibration/frame/${source}`);
                    const mapResp = await fetch(`/calibration/map-preview/${map}`);
                    
                    if (!frameResp.ok || !mapResp.ok) throw new Error('Error cargando datos');
                    
                    const frameData = await frameResp.json();
                    const mapData = await mapResp.json();
                    
                    // Establecer contexto ANTES de agregar puntos
                    const contextResp = await fetch('/calibration/set-context', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ source, map })
                    });
                    
                    if (!contextResp.ok) throw new Error('Error estableciendo contexto');
                    
                    const img = new Image();
                    img.onload = () => {
                        canvas.width = img.width;
                        canvas.height = img.height;
                        ctx.drawImage(img, 0, 0);
                        frameImage = img;
                        redrawCanvasPoints();
                    };
                    img.src = `data:image/png;base64,${frameData.frame}`;
                    
                    mapContainer.innerHTML = mapData.svg;
                    mapSvg = mapContainer.querySelector('svg');
                    
                    // Limpiar etiquetas OSM del mapa
                    const textElements = mapSvg.querySelectorAll('text');
                    textElements.forEach(el => el.remove());
                    
                    redrawMapPoints();
                    
                    calibrationSection.classList.remove('hidden');
                    step1Status.textContent = '✓ Listo. Calibra los puntos arriba →';
                    step1Status.classList.add('success');
                    
                    pixelPoints = [];
                    worldPoints = [];
                    updatePointsList();
                } catch (err) {
                    step1Status.textContent = '❌ Error cargando datos: ' + err.message;
                    step1Status.classList.add('error');
                }
            }
            
            function redrawCanvasPoints() {
                if (!frameImage) return;
                ctx.drawImage(frameImage, 0, 0);
                pixelPoints.forEach((p, i) => {
                    ctx.fillStyle = '#00ff88';
                    ctx.beginPath();
                    ctx.arc(p[0], p[1], 8, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.strokeStyle = '#00a5ff';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                    
                    ctx.fillStyle = '#00a5ff';
                    ctx.font = 'bold 14px Arial';
                    ctx.fillText((i + 1).toString(), p[0] + 12, p[1] - 8);
                });
            }
            
            function redrawMapPoints() {
                if (!mapSvg) return;
                const existingCircles = mapSvg.querySelectorAll('circle[data-calib-point]');
                existingCircles.forEach(c => c.remove());
                
                worldPoints.forEach((p, i) => {
                    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                    circle.setAttribute('cx', p[0]);
                    circle.setAttribute('cy', p[1]);
                    circle.setAttribute('r', '0.1');  // ← RADIO DEL CÍRCULO NARANJA (en unidades SVG)
                    circle.setAttribute('fill', '#ff6600');
                    circle.setAttribute('stroke', '#ffaa00');
                    circle.setAttribute('stroke-width', '2');
                    circle.setAttribute('data-calib-point', i);
                    circle.setAttribute('opacity', '0.8');
                    mapSvg.appendChild(circle);
                });
            }
            
            canvas.addEventListener('click', (e) => {
                if (!frameImage) return;
                
                const rect = canvas.getBoundingClientRect();
                const x = (e.clientX - rect.left) * (canvas.width / rect.width);
                const y = (e.clientY - rect.top) * (canvas.height / rect.height);
                
                pixelPoints.push([Math.round(x), Math.round(y)]);
                redrawCanvasPoints();
                clickMode = 'world';
                step2Status.textContent = '👉 Ahora haz clic en el mapa para marcar la coordenada en metros';
                updatePointsList();
            });
            
            mapContainer.addEventListener('click', (e) => {
                if (!mapSvg || pixelPoints.length <= worldPoints.length) return;
                
                // Transformar coordenadas del click al espacio SVG
                const pt = mapSvg.createSVGPoint();
                pt.x = e.clientX;
                pt.y = e.clientY;
                
                const screenCTM = mapSvg.getScreenCTM();
                if (!screenCTM) return;
                
                const svgPt = pt.matrixTransform(screenCTM.inverse());
                
                // Guardar coordenadas directas del SVG (ya están invertidas en el backend)
                worldPoints.push([Math.round(svgPt.x), Math.round(svgPt.y)]);
                redrawMapPoints();
                clickMode = 'pixel';
                step2Status.textContent = '';
                updatePointsList();
                
                if (pixelPoints.length >= 4 && worldPoints.length >= 4) {
                    calcBtn.disabled = false;
                    step2Status.textContent = '✓ Suficientes puntos. Puedes calcular la matriz.';
                    step2Status.classList.add('success');
                }
            });
            
            function updatePointsList() {
                pixelsList.innerHTML = '<strong style="color: #00a5ff;">Puntos píxeles:</strong>';
                pixelPoints.forEach((p, i) => {
                    pixelsList.innerHTML += `<div class="point-item">${i + 1}. [${p[0]}, ${p[1]}]</div>`;
                });
                
                worldList.innerHTML = '<strong style="color: #00a5ff;">Puntos mundo:</strong>';
                worldPoints.forEach((p, i) => {
                    worldList.innerHTML += `<div class="point-item">${i + 1}. [${p[0]}, ${p[1]}]</div>`;
                });
            }
            
            clearBtn.addEventListener('click', async () => {
                try {
                    pixelPoints = [];
                    worldPoints = [];
                    calcBtn.disabled = true;
                    step2Status.textContent = '';
                    updatePointsList();
                    redrawCanvasPoints();
                    redrawMapPoints();
                    await fetch('/calibration/clear', { method: 'POST' });
                } catch (err) {
                    step2Status.textContent = '❌ Error limpiando puntos';
                }
            });
            
            calcBtn.addEventListener('click', async () => {
                try {
                    step2Status.textContent = '⏳ Agregando puntos...';
                    
                    for (let i = 0; i < pixelPoints.length; i++) {
                        const result = await fetch('/calibration/add-point', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                point_px: pixelPoints[i],
                                point_world: worldPoints[i]
                            })
                        });
                        
                        if (!result.ok) {
                            const err = await result.json();
                            throw new Error(`Punto ${i + 1}: ${err.error || result.statusText}`);
                        }
                    }
                    
                    step2Status.textContent = '⏳ Calculando matriz...';
                    const calcResp = await fetch('/calibration/calculate', { method: 'POST' });
                    const calcResult = await calcResp.json();
                    
                    if (calcResult.success) {
                        step2Status.textContent = '✓ Matriz H calculada exitosamente';
                        step2Status.classList.add('success');
                        
                        setTimeout(() => {
                            calibrationSection.classList.add('hidden');
                            successSection.classList.remove('hidden');
                        }, 1000);
                    } else {
                        throw new Error(calcResult.message || 'Error desconocido');
                    }
                } catch (err) {
                    step2Status.textContent = '❌ Error: ' + err.message;
                    step2Status.classList.add('error');
                }
            });
            
            backBtn.addEventListener('click', () => {
                calibrationSection.classList.add('hidden');
                successSection.classList.add('hidden');
                pixelPoints = [];
                worldPoints = [];
                updatePointsList();
                sourceSelect.value = '';
                mapSelect.value = '';
                step1Status.textContent = '';
            });
            
            sourceSelect.addEventListener('change', loadCalibrationData);
            mapSelect.addEventListener('change', loadCalibrationData);
            
            loadOptions();
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/dashboard')
def dashboard():
    """Dashboard - Reproducir video + KPIs (Calibración ya realizada)"""
    html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Gemelo Digital - Panel de Percepción</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #fff;
                min-height: 100vh;
                padding: 20px;
            }

            .container {
                max-width: 1600px;
                margin: 0 auto;
            }

            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                border-bottom: 2px solid #00a5ff;
                padding-bottom: 15px;
            }

            .header h1 {
                color: #00a5ff;
                font-size: 2em;
            }

            .btn-change-content {
                background: rgba(255, 165, 0, 0.2);
                border: 2px solid #ffa500;
                color: #ffa500;
                padding: 10px 20px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                font-size: 1em;
                transition: all 0.3s;
            }

            .btn-change-content:hover {
                background: rgba(255, 165, 0, 0.3);
                transform: translateY(-2px);
            }

            .content {
                display: grid;
                grid-template-columns: 2fr 1fr;
                gap: 20px;
            }

            .video-section {
                background: rgba(0, 20, 40, 0.9);
                border: 2px solid #00a5ff;
                border-radius: 12px;
                padding: 15px;
                overflow: hidden;
            }

            .video-section h2 {
                color: #00a5ff;
                margin-bottom: 15px;
                font-size: 1.2em;
            }

            .video-stream {
                width: 100%;
                height: auto;
                display: block;
                background: #000;
                border-radius: 8px;
            }

            .metrics-section {
                background: linear-gradient(135deg, #0f3460, #16213e);
                border: 2px solid #00d4ff;
                border-radius: 12px;
                padding: 20px;
                overflow-y: auto;
                max-height: 800px;
            }

            .metrics-section h2 {
                color: #00d4ff;
                margin-bottom: 10px;
                font-size: 1.1em;
            }

            .metric {
                background: rgba(0, 165, 255, 0.1);
                padding: 12px;
                margin-bottom: 10px;
                border-left: 4px solid #00a5ff;
                border-radius: 4px;
            }

            .metric-label {
                color: #aaa;
                font-size: 0.9em;
                text-transform: uppercase;
            }

            .metric-value {
                color: #00ff88;
                font-size: 1.4em;
                font-weight: bold;
                margin-top: 5px;
            }

            .json-data {
                background: #000;
                border: 1px solid #333;
                padding: 10px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                font-size: 0.7em;
                max-height: 300px;
                overflow: auto;
                color: #00ff88;
            }

            @media (max-width: 1200px) {
                .content {
                    grid-template-columns: 1fr;
                }

                .metrics-section {
                    max-height: none;
                }
            }

            ::-webkit-scrollbar {
                width: 8px;
            }

            ::-webkit-scrollbar-track {
                background: #0f3460;
            }

            ::-webkit-scrollbar-thumb {
                background: #00a5ff;
                border-radius: 4px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Dashboard - Monitoreo de Tráfico</h1>
                <button class="btn-change-content" onclick="window.location.href='/';">🔄 Cambiar Contenido</button>
            </div>
            
            <div class="content">
                <div class="video-section">
                    <h2>📹 Video Stream en Vivo</h2>
                    <img class="video-stream" src="/video_feed" alt="Video Stream - Cargando...">
                </div>
                
                <div class="metrics-section">
                    <h2>📊 Métricas en Tiempo Real</h2>
                    <p style="color: #aaa; font-size: 0.9em; margin-bottom: 15px;">
                        Estos datos se envían a SUMO para simulación de tráfico
                    </p>
                    
                    <div class="metric">
                        <div class="metric-label">Total de Vehículos</div>
                        <div class="metric-value" id="total-vehicles">-</div>
                    </div>
                    
                    <div class="metric">
                        <div class="metric-label">Nivel de Congestión</div>
                        <div class="metric-value" id="congestion">-</div>
                    </div>
                    
                    <div class="metric">
                        <div class="metric-label">Densidad (0-1)</div>
                        <div class="metric-value" id="density">-</div>
                    </div>
                    
                    <div class="metric">
                        <div class="metric-label">Estado</div>
                        <div id="status-badge"></div>
                    </div>
                    
                    <div class="metric">
                        <div class="metric-label">Conteos por Tipo</div>
                        <div class="metric-value" id="counts" style="font-size: 0.9em; line-height: 1.6;"></div>
                    </div>
                    
                    <div class="metric">
                        <div class="metric-label">Detecciones (JSON)</div>
                        <pre class="json-data" id="json-data">Cargando...</pre>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            async function updateData() {
                try {
                    const response = await fetch('/detections');
                    const data = await response.json();
                    
                    document.getElementById('total-vehicles').textContent = data.total || 0;
                    document.getElementById('congestion').textContent = data.congestion || 'N/A';
                    document.getElementById('density').textContent = (data.density || 0).toFixed(3);
                    
                    let counts = '';
                    for (const [type, count] of Object.entries(data.counts || {})) {
                        counts += `${type}: ${count}\\n`;
                    }
                    document.getElementById('counts').textContent = counts || 'N/A';
                    
                    const status = data.status_stream === 'online' ? '🟢 EN VIVO' : '🔴 OFFLINE';
                    const statusColor = data.status_stream === 'online' ? '#00aa00' : '#ff0000';
                    document.getElementById('status-badge').innerHTML = `<span style="background: ${statusColor}; color: #fff; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.8em;">${status}</span>`;
                    
                    document.getElementById('json-data').textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    console.error('Error updating data:', error);
                }
            }
            
            updateData();
            setInterval(updateData, 500);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


def start_server(host='0.0.0.0', port=5000, debug=False):
    global detector_thread

    # Registrar signal handlers para shutdown seguro
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigterm)

    print("\n[SERVER] Registrando signal handlers...")
    print("[SERVER] Presiona Ctrl+C para shutdown seguro")

    detector_thread = start_detector_thread()
    print(f"[SERVER] Starting Flask on {host}:{port}")
    print(f"[SERVER] Open http://localhost:{port}/ in your browser")

    try:
        app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[SERVER] Flask interrupted")
    finally:
        print("[SERVER] Limpiando...")
        signal_shutdown()
        sys.exit(0)

if __name__ == '__main__':
    start_server()
