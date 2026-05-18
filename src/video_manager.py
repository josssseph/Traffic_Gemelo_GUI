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
            
            # Calcular bounding box
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
            
            # Padding
            padding = 50
            width = int(max_x - min_x) + 2 * padding
            height = int(max_y - min_y) + 2 * padding
            
            if width < 100 or height < 100:
                width = 800
                height = 600
            
            # Crear SVG con viewBox para responsividad
            svg_lines = [
                f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" style="max-width: 100%; height: auto; width: 100%;">',
                '<style>',
                '  .edge { stroke: #333; stroke-width: 2; fill: none; }',
                '  .junction { fill: #0066cc; }',
                '  .junction-label { font-size: 8px; fill: white; text-anchor: middle; }',
                '</style>',
                f'<rect width="{width}" height="{height}" fill="#f0f0f0"/>'
            ]
            
            # Dibujar edges (calles)
            for edge in edges:
                lane_elements = edge.findall('.//lane')
                for lane in lane_elements:
                    shape = lane.get('shape', '')
                    if shape:
                        points = []
                        for coord in shape.split():
                            x, y = map(float, coord.split(','))
                            px = int((x - min_x) + padding)
                            py = int((y - min_y) + padding)
                            points.append(f"{px},{py}")
                        
                        if points:
                            points_str = ' '.join(points)
                            svg_lines.append(f'<polyline class="edge" points="{points_str}"/>')
            
            # Dibujar junctions (intersecciones)
            for junction in junctions:
                x = float(junction.get('x', 0))
                y = float(junction.get('y', 0))
                jid = junction.get('id', '')
                
                px = int((x - min_x) + padding)
                py = int((y - min_y) + padding)
                
                svg_lines.append(f'<circle cx="{px}" cy="{py}" r="4" class="junction"/>')
                if len(jid) < 10:  # Solo labels cortos
                    svg_lines.append(f'<text x="{px}" y="{py+8}" class="junction-label">{jid}</text>')
            
            svg_lines.append('</svg>')
            return '\n'.join(svg_lines)
            
        except Exception as e:
            print(f"[NETWORK] Error converting to SVG: {e}")
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
