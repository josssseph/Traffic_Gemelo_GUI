"""
Gestor de Matrices de Homografía para Mapeo Video→Mundo
Permite calibración interactiva y persistencia de matrices H
"""

import numpy as np
import cv2
import pickle
import json
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class CalibrationManager:
    """
    Gestiona puntos de calibración y matrices de homografía
    para múltiples fuentes de video y mapas
    """
    
    def __init__(self, calibration_dir: str = 'calibration'):
        self.calibration_dir = Path(calibration_dir)
        self.calibration_dir.mkdir(exist_ok=True)
        
        # Estado actual de calibración
        self.current_source = None
        self.current_map = None
        self.current_points = {'video': [], 'world': []}
        
        # Matrices de homografía cargadas
        self.homographies: Dict[str, np.ndarray] = {}
        self.metadata: Dict[str, dict] = {}
        
        # Lock para thread-safety
        self.lock = threading.RLock()
        
        # Cargar calibraciones existentes
        self._load_existing_calibrations()
    
    def _load_existing_calibrations(self):
        """Carga todas las matrices H guardadas y sus metadatos"""
        for pkl_file in self.calibration_dir.glob('*.pkl'):
            source = pkl_file.stem
            try:
                with open(pkl_file, 'rb') as f:
                    self.homographies[source] = pickle.load(f)
                
                # Intentar cargar metadatos
                metadata_file = self.calibration_dir / f'{source}_metadata.json'
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        self.metadata[source] = json.load(f)
                
                print(f"[CALIB] Loaded homography: {source}")
            except Exception as e:
                print(f"[CALIB] Error loading {source}: {e}")
    
    def set_calibration_context(self, source: str, map_file: str):
        """
        Establece la fuente de video y mapa para calibración
        Limpia puntos anteriores si cambió de contexto
        """
        with self.lock:
            if source != self.current_source or map_file != self.current_map:
                print(f"[CALIB] Contexto cambiado: {self.current_source} → {source}, map: {map_file}")
                self.current_source = source
                self.current_map = map_file
                self.current_points = {'video': [], 'world': []}
                return True
            return False
    
    def add_point(self, point_px: Tuple[float, float], point_world: Tuple[float, float]) -> Dict:
        """
        Agrega un punto de calibración
        
        Args:
            point_px: (x, y) en píxeles del video
            point_world: (x, y) en coordenadas del mapa SUMO
        
        Returns:
            dict con información del punto agregado
        """
        with self.lock:
            if not self.current_source or not self.current_map:
                return {'error': 'No context set', 'success': False}
            
            self.current_points['video'].append(point_px)
            self.current_points['world'].append(point_world)
            
            num_points = len(self.current_points['video'])
            precision = self._estimate_precision(num_points)
            
            print(f"[CALIB] Punto agregado {num_points}: {point_px} → {point_world}")
            
            result = {
                'success': True,
                'point_number': num_points,
                'point_px': point_px,
                'point_world': point_world,
                'precision': precision,
                'can_calculate': num_points >= 4
            }
            
            # Si tenemos 4+ puntos, calcular automáticamente
            if num_points >= 4:
                h_result = self.calculate_homography()
                result['homography_calculated'] = h_result['success']
                if h_result['success']:
                    result['homography_error'] = h_result.get('error', None)
            
            return result
    
    def clear_current_points(self):
        """Limpia los puntos actuales sin afectar guardados"""
        with self.lock:
            self.current_points = {'video': [], 'world': []}
            print(f"[CALIB] Puntos limpiados para {self.current_source}")
    
    def calculate_homography(self) -> Dict:
        """
        Calcula la matriz H usando los puntos actuales
        
        Returns:
            dict con resultado del cálculo
        """
        with self.lock:
            if not self.current_source:
                return {'success': False, 'error': 'No source set'}
            
            num_points = len(self.current_points['video'])
            if num_points < 4:
                return {
                    'success': False,
                    'error': f'Need at least 4 points, got {num_points}'
                }
            
            try:
                points_px = np.array(self.current_points['video'], dtype=np.float32)
                points_world = np.array(self.current_points['world'], dtype=np.float32)
                
                # Calcular homografía usando SVD
                H, status = cv2.findHomography(points_px, points_world)
                
                if H is None:
                    return {'success': False, 'error': 'findHomography failed'}
                
                # Calcular error de reprojección
                reprojected = cv2.perspectiveTransform(
                    points_px.reshape(-1, 1, 2), H
                ).reshape(-1, 2)
                
                errors = np.linalg.norm(reprojected - points_world, axis=1)
                mean_error = np.mean(errors)
                max_error = np.max(errors)
                
                # Guardar matriz
                self.homographies[self.current_source] = H
                self.metadata[self.current_source] = {
                    'timestamp': __import__('time').time(),
                    'num_points': num_points,
                    'map_file': self.current_map,
                    'mean_error': float(mean_error),
                    'max_error': float(max_error),
                    'points': {
                        'video': self.current_points['video'].copy(),
                        'world': self.current_points['world'].copy()
                    }
                }
                
                # Persistir
                self._save_homography(self.current_source, H)
                
                print(f"[CALIB] H calculada: mean_error={mean_error:.4f}, max_error={max_error:.4f}")
                
                return {
                    'success': True,
                    'mean_error': float(mean_error),
                    'max_error': float(max_error),
                    'matrix': H.tolist()
                }
            
            except Exception as e:
                print(f"[CALIB] Error calculating H: {e}")
                return {'success': False, 'error': str(e)}
    
    def _save_homography(self, source: str, H: np.ndarray):
        """Persiste matriz H a disco"""
        try:
            pkl_path = self.calibration_dir / f'{source}.pkl'
            with open(pkl_path, 'wb') as f:
                pickle.dump(H, f)
            
            json_path = self.calibration_dir / f'{source}_metadata.json'
            with open(json_path, 'w') as f:
                json.dump(self.metadata[source], f, indent=2)
            
            print(f"[CALIB] Guardado: {pkl_path}")
        except Exception as e:
            print(f"[CALIB] Error saving H: {e}")
    
    def get_homography(self, source: str) -> Optional[np.ndarray]:
        """Obtiene matriz H para una fuente"""
        with self.lock:
            return self.homographies.get(source)
    
    def get_homography_list(self) -> Dict[str, dict]:
        """Retorna lista de todas las matrices H calibradas"""
        with self.lock:
            result = {}
            for source, H in self.homographies.items():
                meta = self.metadata.get(source, {})
                result[source] = {
                    'calibrated': True,
                    'timestamp': meta.get('timestamp'),
                    'num_points': meta.get('num_points'),
                    'map_file': meta.get('map_file'),
                    'mean_error': meta.get('mean_error'),
                    'max_error': meta.get('max_error')
                }
            return result
    
    def pixel_to_world(self, source: str, x_px: float, y_px: float) -> Optional[Tuple[float, float]]:
        """
        Transforma coordenadas píxel → mundo usando homografía
        
        Args:
            source: nombre de la fuente (live, respaldo1, etc)
            x_px, y_px: coordenadas en píxeles
        
        Returns:
            (x_world, y_world) o None si no está calibrada
        """
        H = self.get_homography(source)
        if H is None:
            return None
        
        try:
            point = np.array([[x_px], [y_px], [1]], dtype=np.float32)
            world = H @ point
            
            # Normalizar coordenadas homogéneas
            x_world = float(world[0, 0] / world[2, 0])
            y_world = float(world[1, 0] / world[2, 0])
            
            return (x_world, y_world)
        except Exception as e:
            print(f"[CALIB] Error in pixel_to_world: {e}")
            return None
    
    def get_current_state(self) -> Dict:
        """Retorna estado actual de calibración"""
        with self.lock:
            return {
                'source': self.current_source,
                'map': self.current_map,
                'points_added': len(self.current_points['video']),
                'can_calculate': len(self.current_points['video']) >= 4,
                'current_points': {
                    'video': self.current_points['video'].copy(),
                    'world': self.current_points['world'].copy()
                }
            }
    
    def _estimate_precision(self, num_points: int) -> str:
        """Estima precisión basada en número de puntos"""
        if num_points < 4:
            return 'insufficient'
        elif num_points == 4:
            return 'low'
        elif num_points < 8:
            return 'medium'
        else:
            return 'high'


# Instancia global
calibration_manager = CalibrationManager(calibration_dir='calibration')
