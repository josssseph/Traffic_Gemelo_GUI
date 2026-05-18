"""
Buffer Manager: Almacenamiento circular thread-safe de frames
Mantiene 15 segundos de video crudo sin comprimir para sincronización temporal
"""

import threading
import time
from collections import deque
import numpy as np


class BufferManager:
    """
    Gestiona un buffer circular de frames con timestamps.
    - Thread-safe con locks
    - Automático: elimina frames viejos
    - Permite consultas por índice o por timestamp
    """

    def __init__(self, buffer_duration_seconds=15, expected_fps=16):
        """
        Args:
            buffer_duration_seconds: Duración del buffer (default 15s)
            expected_fps: FPS esperados del detector (default 16)
        """
        self.buffer_duration = buffer_duration_seconds
        self.expected_fps = expected_fps
        self.max_frames = int(buffer_duration_seconds * expected_fps)

        self.frames = deque(maxlen=self.max_frames)
        self.timestamps = deque(maxlen=self.max_frames)
        self.metadata = deque(maxlen=self.max_frames)  # Info adicional (JSON data)

        self.lock = threading.RLock()
        self.frame_count = 0

    def push(self, frame, timestamp=None, metadata=None):
        """
        Agregar frame al buffer.

        Args:
            frame: numpy array de imagen
            timestamp: float unix timestamp (auto-generado si es None)
            metadata: dict con información adicional (detecciones JSON, etc)
        """
        if timestamp is None:
            timestamp = time.time()

        with self.lock:
            # Copiar frame para evitar que sea modificado externamente
            frame_copy = frame.copy()
            self.frames.append(frame_copy)
            self.timestamps.append(timestamp)
            self.metadata.append(metadata or {})
            self.frame_count += 1

    def get_latest(self):
        """Obtener el frame más reciente"""
        with self.lock:
            if len(self.frames) == 0:
                return None, None, None
            return (
                self.frames[-1].copy(),
                self.timestamps[-1],
                self.metadata[-1].copy() if self.metadata[-1] else {}
            )

    def get_by_index(self, index):
        """
        Obtener frame por índice (0 = más antiguo, -1 = más reciente)

        Returns:
            (frame, timestamp, metadata) o (None, None, None)
        """
        with self.lock:
            if len(self.frames) == 0 or abs(index) > len(self.frames):
                return None, None, None
            return (
                self.frames[index].copy(),
                self.timestamps[index],
                self.metadata[index].copy() if self.metadata[index] else {}
            )

    def get_by_timestamp(self, target_timestamp):
        """
        Obtener frame más cercano a un timestamp específico.

        Args:
            target_timestamp: float unix timestamp

        Returns:
            (frame, timestamp, metadata) del frame más cercano
        """
        with self.lock:
            if len(self.timestamps) == 0:
                return None, None, None

            # Encontrar índice del timestamp más cercano
            min_diff = float('inf')
            closest_idx = -1

            for i, ts in enumerate(self.timestamps):
                diff = abs(ts - target_timestamp)
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = i

            if closest_idx == -1:
                return None, None, None

            return (
                self.frames[closest_idx].copy(),
                self.timestamps[closest_idx],
                self.metadata[closest_idx].copy() if self.metadata[closest_idx] else {}
            )

    def get_range(self, start_idx, end_idx):
        """
        Obtener rango de frames (para procesamiento batch).

        Args:
            start_idx: índice inicial (inclusive)
            end_idx: índice final (exclusive)

        Returns:
            list of (frame, timestamp, metadata) tuples
        """
        with self.lock:
            result = []
            buffer_len = len(self.frames)

            for i in range(max(0, start_idx), min(buffer_len, end_idx)):
                result.append((
                    self.frames[i].copy(),
                    self.timestamps[i],
                    self.metadata[i].copy() if self.metadata[i] else {}
                ))

            return result

    def get_all(self):
        """Obtener todos los frames del buffer"""
        with self.lock:
            result = []
            for i in range(len(self.frames)):
                result.append((
                    self.frames[i].copy(),
                    self.timestamps[i],
                    self.metadata[i].copy() if self.metadata[i] else {}
                ))
            return result

    def size(self):
        """Número actual de frames en el buffer"""
        with self.lock:
            return len(self.frames)

    def duration(self):
        """Duración actual del contenido en segundos"""
        with self.lock:
            if len(self.timestamps) < 2:
                return 0.0
            return self.timestamps[-1] - self.timestamps[0]

    def clear(self):
        """Limpiar el buffer completamente"""
        with self.lock:
            self.frames.clear()
            self.timestamps.clear()
            self.metadata.clear()
            self.frame_count = 0

    def get_stats(self):
        """Obtener estadísticas del buffer"""
        with self.lock:
            return {
                'total_frames_ever': self.frame_count,
                'current_frames': len(self.frames),
                'max_capacity': self.max_frames,
                'buffer_duration_seconds': self.duration(),
                'oldest_timestamp': self.timestamps[0] if len(self.timestamps) > 0 else None,
                'newest_timestamp': self.timestamps[-1] if len(self.timestamps) > 0 else None,
            }


# Instancia global (singleton)
buffer_manager = BufferManager(buffer_duration_seconds=5, expected_fps=16)
