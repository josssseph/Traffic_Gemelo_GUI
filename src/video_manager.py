"""
Gestor de Múltiples Fuentes de Video y Mapas
Detecta automáticamente videos en carpeta videos/ y .net en networks/
"""

import cv2
from pathlib import Path
from typing import Dict, Optional, Tuple
import threading

class VideoSourceManager:
    """Gestiona múltiples fuentes de video"""
    
    def __init__(self, videos_dir: str = 'videos', networks_dir: str = 'networks'):
        self.videos_dir = Path(videos_dir)
        self.networks_dir = Path(networks_dir)
        
        # Cache de frames
        self.frame_cache: Dict[str, Tuple] = {}
        self.frame_lock = threading.RLock()
        
        # Detectar fuentes disponibles
        self.video_sources = self._detect_videos()
        self.network_files = self._detect_networks()
        
        print(f"[VIDEO] Fuentes detectadas: {list(self.video_sources.keys())}")
        print(f"[VIDEO] Redes detectadas: {list(self.network_files.keys())}")
    
    def _detect_videos(self) -> Dict[str, str]:
        """Detecta todos los videos en la carpeta videos/"""
        sources = {'live': 'live'}  # 'live' es siempre disponible (stream en vivo)
        
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m3u8']
        
        if self.videos_dir.exists():
            for video_file in self.videos_dir.iterdir():
                if video_file.suffix.lower() in video_extensions:
                    # Nombre sin extensión
                    name = video_file.stem
                    sources[name] = str(video_file)
        
        return sources
    
    def _detect_networks(self) -> Dict[str, str]:
        """Detecta todos los archivos .net en carpeta networks/"""
        networks = {}
        
        if self.networks_dir.exists():
            for net_file in self.networks_dir.glob('*.net*'):  # .net, .net.xml, etc
                name = net_file.stem.replace('.net', '')  # Limpia extensión
                networks[name] = str(net_file)
        
        return networks
    
    def get_frame_from_source(self, source: str, force_refresh: bool = False) -> Optional[bytes]:
        """
        Obtiene frame actual de una fuente de video
        
        Args:
            source: nombre de la fuente (live, respaldo1, respaldo2)
            force_refresh: fuerza lectura nueva en lugar de usar cache
        
        Returns:
            frame como bytes PNG codificados en base64 o None
        """
        import cv2
        import base64
        
        if source not in self.video_sources:
            print(f"[VIDEO] Source not found: {source}")
            return None
        
        try:
            video_path = self.video_sources[source]
            frame = None
            ret = False
            
            # Manejar 'live' especialmente - obtener frame del stream en vivo
            if source == 'live':
                # 'live' usa el stream del servidor (disponible en buffer)
                try:
                    from buffer_manager import buffer_manager
                    frame, _, _ = buffer_manager.get_latest()
                    ret = frame is not None
                except:
                    ret = False
                
                if not ret:
                    # Si no hay frame disponible, crear uno vacío
                    frame = cv2.zeros((480, 640, 3), dtype=cv2.uint8)
                    ret = True
            else:
                # Abrir video grabado y obtener frame actual
                cap = cv2.VideoCapture(video_path)
                ret, frame = cap.read()
                cap.release()
            
            if not ret or frame is None:
                print(f"[VIDEO] Error reading frame from {source}")
                return None
            
            # Codificar a PNG y luego a base64
            _, buffer = cv2.imencode('.png', frame)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return frame_base64
        
        except Exception as e:
            print(f"[VIDEO] Error getting frame: {e}")
            return None
    
    def get_frame_resolution(self, source: str) -> Optional[Tuple[int, int]]:
        """Obtiene resolución (W, H) de una fuente"""
        if source not in self.video_sources:
            return None
        
        try:
            # 'live' usa resolución estándar del stream
            if source == 'live':
                return (640, 480)  # Resolución estándar del stream
            
            cap = cv2.VideoCapture(self.video_sources[source])
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            return (w, h)
        except:
            return None
    
    def get_map_content(self, map_name: str) -> Optional[str]:
        """
        Obtiene contenido del archivo .net (XML)
        
        Args:
            map_name: nombre del mapa (cuenca_respaldo1, etc)
        
        Returns:
            Contenido XML o None
        """
        if map_name not in self.network_files:
            print(f"[NETWORK] Map not found: {map_name}")
            return None
        
        try:
            map_path = self.network_files[map_name]
            with open(map_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"[NETWORK] Error reading map: {e}")
            return None
    
    def get_map_as_svg(self, map_name: str) -> Optional[str]:
        """
        Convierte archivo .net (SUMO XML) a SVG para visualización
        Con soporte para zoom y posicionamiento dinámico
        
        Args:
            map_name: nombre del mapa
        
        Returns:
            SVG string o None
        """
        if map_name not in self.network_files:
            return None
        
        try:
            import xml.etree.ElementTree as ET
            
            map_path = self.network_files[map_name]
            tree = ET.parse(map_path)
            root = tree.getroot()
            
            # Encontrar límites del mapa
            junctions = root.findall('.//junction')
            edges = root.findall('.//edge')
            
            if not junctions:
                return None
            
            # Calcular bounding box de coordenadas reales
            x_coords = []
            y_coords = []
            
            for junction in junctions:
                x = float(junction.get('x', 0))
                y = float(junction.get('y', 0))
                x_coords.append(x)
                y_coords.append(y)
            
            min_x = min(x_coords)
            max_x = max(x_coords)
            min_y = min(y_coords)
            max_y = max(y_coords)
            
            # Padding como % de las dimensiones
            padding_pct = 0.1
            x_range = max_x - min_x
            y_range = max_y - min_y
            
            x_padding = x_range * padding_pct if x_range > 0 else 50
            y_padding = y_range * padding_pct if y_range > 0 else 50
            
            viewbox_min_x = min_x - x_padding
            viewbox_min_y = min_y - y_padding
            viewbox_width = x_range + 2 * x_padding
            viewbox_height = y_range + 2 * y_padding
            
            # Garantizar tamaño mínimo
            if viewbox_width < 100:
                viewbox_width = 100
                viewbox_min_x = (min_x + max_x) / 2 - 50
            if viewbox_height < 100:
                viewbox_height = 100
                viewbox_min_y = (min_y + max_y) / 2 - 50
            
            # Crear SVG con viewBox dinámico
            svg_lines = [
                f'<svg id="route-map" viewBox="{viewbox_min_x} {viewbox_min_y} {viewbox_width} {viewbox_height}" '
                f'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" '
                f'style="width: 100%; height: 100%; background: #f0f0f0; display: block;">',
                '<defs>',
                '  <style>',
                '    .edge { stroke: #333; stroke-width: 3; fill: none; stroke-linecap: round; }',
                '    .junction { fill: #0066cc; }',
                '    .junction-label { font-size: 10px; fill: white; text-anchor: middle; pointer-events: none; }',
                '  </style>',
                '</defs>',
                f'<rect x="{viewbox_min_x}" y="{viewbox_min_y}" width="{viewbox_width}" height="{viewbox_height}" fill="#f0f0f0"/>'
            ]
            
            # IMPORTANTE: Invertir eje Y (SUMO tiene Y hacia arriba, SVG hacia abajo)
            y_center = (min_y + max_y) / 2
            
            # Dibujar edges (calles)
            for edge in edges:
                lane_elements = edge.findall('.//lane')
                for lane in lane_elements:
                    shape = lane.get('shape', '')
                    if shape:
                        points = []
                        for coord in shape.split():
                            try:
                                x, y = map(float, coord.split(','))
                                # Invertir Y: y_invertido = center - (y - center) = 2*center - y
                                y_inv = 2 * y_center - y
                                points.append(f"{x},{y_inv}")
                            except:
                                continue
                        
                        if len(points) > 1:
                            points_str = ' '.join(points)
                            svg_lines.append(f'<polyline class="edge" points="{points_str}"/>')
            
            # Dibujar junctions (intersecciones)
            for junction in junctions:
                x = float(junction.get('x', 0))
                y = float(junction.get('y', 0))
                jid = junction.get('id', '')
                
                # Invertir Y
                y_inv = 2 * y_center - y
                
                svg_lines.append(f'<circle cx="{x}" cy="{y_inv}" r="5" class="junction"/>')
                if len(jid) < 15:
                    svg_lines.append(f'<text x="{x}" y="{y_inv+12}" class="junction-label">{jid}</text>')
            
            svg_lines.append('</svg>')
            return '\n'.join(svg_lines)
            
        except Exception as e:
            print(f"[NETWORK] Error converting to SVG: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_available_sources(self) -> Dict[str, dict]:
        """Retorna lista de fuentes disponibles con metadata"""
        result = {}
        
        for name, path in self.video_sources.items():
            res = self.get_frame_resolution(name)
            if name == 'live':
                result[name] = {
                    'type': 'live_stream',
                    'path': 'live',
                    'resolution': res,
                    'extension': 'stream'
                }
            else:
                result[name] = {
                    'type': 'video',
                    'path': path,
                    'resolution': res,
                    'extension': Path(path).suffix
                }
        
        return result
    
    def get_available_maps(self) -> Dict[str, dict]:
        """Retorna lista de mapas disponibles con metadata"""
        result = {}
        
        for name, path in self.network_files.items():
            try:
                size_kb = Path(path).stat().st_size / 1024
                result[name] = {
                    'type': 'network',
                    'path': path,
                    'size_kb': size_kb,
                    'extension': Path(path).suffix
                }
            except:
                result[name] = {
                    'type': 'network',
                    'path': path,
                    'size_kb': 0
                }
        
        return result


# Instancia global
video_manager = VideoSourceManager(
    videos_dir='videos',
    networks_dir='networks'
)
