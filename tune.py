#!/usr/bin/env python3
"""
Quick Tuning Tool - Cambiar codecs y parámetros en tiempo real
Requiere que el servidor esté corriendo: python run.py
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

def print_menu():
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
│  9. Cambiar Preprocessing (quality/balanced/fast/none)          │
│  0. Salir                                                       │
└─────────────────────────────────────────────────────────────────┘
    """)

def get_config():
    try:
        response = requests.get(f"{BASE_URL}/codec/config", timeout=2)
        return response.json()
    except Exception as e:
        print(f"❌ Error conectando al servidor: {e}")
        return None

def get_buffer_stats():
    try:
        response = requests.get(f"{BASE_URL}/buffer/stats", timeout=2)
        return response.json()
    except Exception as e:
        print(f"❌ Error: {e}")
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

Estadísticas del Codec:
{json.dumps(config['codec_stats'], indent=2)}
    """)

def print_buffer_stats(stats):
    if not stats:
        return

    print(f"""
╔═ BUFFER CIRCULAR (15 segundos) ════════════════════════════════╗
│  Total frames almacenados: {stats['current_frames']}/{stats['max_capacity']}
│  Duración actual:          {stats['buffer_duration_seconds']:.1f}s
│  Total frames (histórico): {stats['total_frames_ever']}
│  Timestamp antiguo:        {stats['oldest_timestamp']}
│  Timestamp nuevo:          {stats['newest_timestamp']}
╚════════════════════════════════════════════════════════════════╝
    """)

def main():
    print_banner()

    while True:
        print_menu()
        choice = input("Selecciona opción (0-9): ").strip()

        if choice == '1':
            print("\n📊 Obteniendo configuración...\n")
            config = get_config()
            print_config(config)

        elif choice == '2':
            print("\n📊 Obteniendo estadísticas...\n")
            config = get_config()
            if config:
                print(f"Codec: {config['current_codec'].upper()}")
                print(json.dumps(config['codec_stats'], indent=2))

        elif choice == '3':
            print("\n📊 Estadísticas del Buffer...\n")
            stats = get_buffer_stats()
            print_buffer_stats(stats)

        elif choice == '4':
            try:
                quality = int(input("Ingresa calidad JPEG (1-100, default 85): ") or "85")
                quality = max(1, min(100, quality))
                switch_codec('jpeg', quality)
                import time
                time.sleep(1)
                config = get_config()
                print_config(config)
            except ValueError:
                print("❌ Entrada inválida")

        elif choice == '5':
            try:
                quality = int(input("Ingresa calidad WebP (1-100, default 85): ") or "85")
                quality = max(1, min(100, quality))
                switch_codec('webp', quality)
                import time
                time.sleep(1)
                config = get_config()
                print_config(config)
            except ValueError:
                print("❌ Entrada inválida")

        elif choice == '6':
            print("\n✨ Cambiando a Perfil 'Máxima Calidad'...\n")
            print("  - JPEG calidad 95")
            print("  - Preprocessing: quality")
            switch_codec('jpeg', 95)
            switch_preprocessing('quality')
            import time
            time.sleep(1)
            config = get_config()
            print_config(config)

        elif choice == '7':
            print("\n⚡ Cambiando a Perfil 'Balance'...\n")
            print("  - JPEG calidad 80")
            print("  - Preprocessing: balanced")
            switch_codec('jpeg', 80)
            switch_preprocessing('balanced')
            import time
            time.sleep(1)
            config = get_config()
            print_config(config)

        elif choice == '8':
            print("\n🚀 Cambiando a Perfil 'Máxima Velocidad'...\n")
            print("  - JPEG calidad 60")
            print("  - Preprocessing: none (SIN filtros)")
            switch_codec('jpeg', 60)
            switch_preprocessing('none')
            import time
            time.sleep(1)
            config = get_config()
            print_config(config)

        elif choice == '9':
            print("\nOpciones de Preprocessing:")
            print("  1. quality    - Filtros agresivos (máxima calidad, LENTO)")
            print("  2. balanced   - Filtros moderados (PESADO)")
            print("  3. fast       - Solo resize (RÁPIDO)")
            print("  4. none       - Sin filtros (MÁS RÁPIDO)")
            preset_choice = input("Elige: ").strip()
            presets = {'1': 'quality', '2': 'balanced', '3': 'fast', '4': 'none'}
            if preset_choice in presets:
                switch_preprocessing(presets[preset_choice])
                import time
                time.sleep(1)
                config = get_config()
                print_config(config)
            else:
                print("❌ Opción inválida")

        elif choice == '0':
            print("\n👋 ¡Hasta luego!\n")
            break

        else:
            print("❌ Opción inválida")

        input("\nPresiona ENTER para continuar...")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Herramienta de tuning cerrada.\n")
        sys.exit(0)
