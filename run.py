#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from server import start_server

if __name__ == '__main__':
    print("=" * 60)
    print("TRAFFIC GEMELO - Detection & API Server")
    print("=" * 60)
    print("[1] Cargando modelo YOLOv8 en GPU...")
    print("[2] Iniciando hilo de detección...")
    print("[3] Levantando servidor Flask en http://0.0.0.0:5000")
    print()
    print("Endpoints disponibles:")
    print("  GET http://localhost:5000/detections")
    print("  GET http://localhost:5000/health")
    print()
    print("Presiona Ctrl+C para detener.")
    print("=" * 60)
    print()

    start_server(host='0.0.0.0', port=5000, debug=False)
