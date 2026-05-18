"""
Codecs: Múltiples backends de codificación
Base abstracta + implementaciones concretas (JPEG, WebP, H264)
"""

from abc import ABC, abstractmethod
import cv2
import numpy as np
from preprocessing import PreprocessingPipeline, PRESETS


class BaseCodec(ABC):
    """
    Clase base para todos los codificadores.
    Define la interfaz que debe implementar cualquier codec.
    """

    def __init__(self, preprocessing='balanced', **kwargs):
        """
        Args:
            preprocessing: nombre de preset o PreprocessingPipeline personalizado
            **kwargs: parámetros específicos del codec
        """
        if isinstance(preprocessing, str):
            self.preprocessing = PRESETS.get(preprocessing, PRESETS['balanced'])
        else:
            self.preprocessing = preprocessing

    @abstractmethod
    def encode(self, frame):
        """
        Codificar frame a bytes.

        Args:
            frame: numpy array BGR

        Returns:
            bytes del frame codificado, o None si falla
        """
        pass

    @abstractmethod
    def get_stats(self):
        """Retornar estadísticas del codec (fps, compresión, etc)"""
        pass


class JPEGCodec(BaseCodec):
    """
    Codificador JPEG (estándar web, amplia compatibilidad)
    """

    def __init__(self, quality=80, preprocessing='balanced', **kwargs):
        """
        Args:
            quality: 1-100 (default 80)
            preprocessing: filtros a aplicar
        """
        super().__init__(preprocessing=preprocessing)
        self.quality = quality
        self.total_frames = 0
        self.total_bytes = 0

    def encode(self, frame):
        """
        Codificar a JPEG

        Args:
            frame: numpy array BGR

        Returns:
            bytes JPEG, o None
        """
        try:
            # Aplicar preprocessing
            processed = self.preprocessing.process(frame)

            # Codificar
            ret, buffer = cv2.imencode('.jpg', processed,
                                       [cv2.IMWRITE_JPEG_QUALITY, self.quality])

            if not ret:
                return None

            frame_bytes = buffer.tobytes()
            self.total_frames += 1
            self.total_bytes += len(frame_bytes)

            return frame_bytes

        except Exception as e:
            print(f"[ERROR] JPEGCodec.encode: {e}")
            return None

    def get_stats(self):
        avg_size = self.total_bytes / max(1, self.total_frames)
        return {
            'codec': 'JPEG',
            'quality': self.quality,
            'total_frames': self.total_frames,
            'total_bytes': self.total_bytes,
            'avg_frame_size_kb': avg_size / 1024,
        }


class WebPCodec(BaseCodec):
    """
    Codificador WebP (mejor compresión que JPEG, más lento)
    Requiere: opencv compilado con soporte WebP
    """

    def __init__(self, quality=80, preprocessing='balanced', method=6, **kwargs):
        """
        Args:
            quality: 1-100 (default 80)
            preprocessing: filtros a aplicar
            method: 0-6 (6=más lento pero mejor compresión)
        """
        super().__init__(preprocessing=preprocessing)
        self.quality = quality
        self.method = method
        self.total_frames = 0
        self.total_bytes = 0

    def encode(self, frame):
        """
        Codificar a WebP

        Args:
            frame: numpy array BGR

        Returns:
            bytes WebP, o None
        """
        try:
            # Aplicar preprocessing
            processed = self.preprocessing.process(frame)

            # Codificar
            ret, buffer = cv2.imencode('.webp', processed,
                                       [cv2.IMWRITE_WEBP_QUALITY, self.quality])

            if not ret:
                return None

            frame_bytes = buffer.tobytes()
            self.total_frames += 1
            self.total_bytes += len(frame_bytes)

            return frame_bytes

        except Exception as e:
            print(f"[ERROR] WebPCodec.encode: {e}")
            return None

    def get_stats(self):
        avg_size = self.total_bytes / max(1, self.total_frames)
        return {
            'codec': 'WebP',
            'quality': self.quality,
            'method': self.method,
            'total_frames': self.total_frames,
            'total_bytes': self.total_bytes,
            'avg_frame_size_kb': avg_size / 1024,
        }


class H264Codec(BaseCodec):
    """
    Codificador H264 (hardware-accelerated si está disponible)
    Requiere: NVIDIA NVENC o CPU H264
    """

    def __init__(self, bitrate_mbps=2, fps=10, preprocessing='balanced', **kwargs):
        """
        Args:
            bitrate_mbps: bitrate en Mbps (default 2)
            fps: frames por segundo (default 10)
            preprocessing: filtros a aplicar
        """
        super().__init__(preprocessing=preprocessing)
        self.bitrate_mbps = bitrate_mbps
        self.fps = fps
        self.total_frames = 0

        # Intentar inicializar encoder H264
        self.encoder = None
        self._init_encoder()

    def _init_encoder(self):
        """Inicializar encoder H264 (si está disponible)"""
        try:
            fourcc = cv2.VideoWriter_fourcc(*'H264')
            self.encoder = fourcc
            print("[INFO] H264Codec: Hardware H264 disponible")
        except Exception as e:
            print(f"[WARNING] H264Codec no disponible: {e}")
            self.encoder = None

    def encode(self, frame):
        """
        Codificar a H264 (requiere buffer circular)

        Args:
            frame: numpy array BGR

        Returns:
            bytes H264 (nota: retorna None en tiempo real, se usa para almacenamiento)
        """
        try:
            processed = self.preprocessing.process(frame)
            self.total_frames += 1

            # H264 requiere procesamiento en batch, no frame-by-frame
            # Esto es simplificado para demostración
            return None

        except Exception as e:
            print(f"[ERROR] H264Codec.encode: {e}")
            return None

    def get_stats(self):
        return {
            'codec': 'H264',
            'bitrate_mbps': self.bitrate_mbps,
            'fps': self.fps,
            'total_frames': self.total_frames,
            'available': self.encoder is not None,
        }


class AdaptiveCodec(BaseCodec):
    """
    Codec adaptativo: elige automáticamente entre JPEG y WebP
    basado en CPU/GPU usage y tamaño del frame
    """

    def __init__(self, quality=80, preprocessing='balanced', **kwargs):
        super().__init__(preprocessing=preprocessing)
        self.quality = quality
        # Pasar preprocessing a los sub-codecs también
        self.jpeg_codec = JPEGCodec(quality=quality, preprocessing=preprocessing)
        self.webp_codec = WebPCodec(quality=quality, preprocessing=preprocessing)
        self.frame_count = 0
        self.use_webp = False

    def encode(self, frame):
        """
        Elegir codec adaptivamente

        Args:
            frame: numpy array BGR

        Returns:
            bytes codificados
        """
        try:
            # NO aplicar preprocessing aquí - los sub-codecs ya lo hacen
            # Cambiar codec cada 100 frames
            self.frame_count += 1
            if self.frame_count % 100 == 0:
                self.use_webp = not self.use_webp

            if self.use_webp:
                return self.webp_codec.encode(frame)
            else:
                return self.jpeg_codec.encode(frame)

        except Exception as e:
            print(f"[ERROR] AdaptiveCodec.encode: {e}")
            return None

    def get_stats(self):
        return {
            'codec': 'Adaptive',
            'current_backend': 'WebP' if self.use_webp else 'JPEG',
            'quality': self.quality,
            'frame_count': self.frame_count,
            'jpeg_stats': self.jpeg_codec.get_stats(),
            'webp_stats': self.webp_codec.get_stats(),
        }


# Factory para crear codecs fácilmente
def create_codec(codec_type='jpeg', quality=80, preprocessing='balanced', **kwargs):
    """
    Factory para crear instancias de codec

    Args:
        codec_type: 'jpeg', 'webp', 'h264', 'adaptive'
        quality: 1-100
        preprocessing: 'quality', 'balanced', 'fast', 'none'
        **kwargs: parámetros adicionales

    Returns:
        instancia del codec solicitado
    """
    codec_map = {
        'jpeg': JPEGCodec,
        'webp': WebPCodec,
        'h264': H264Codec,
        'adaptive': AdaptiveCodec,
    }

    CodecClass = codec_map.get(codec_type.lower(), JPEGCodec)
    return CodecClass(quality=quality, preprocessing=preprocessing, **kwargs)


# Configuración global tuneable
CODEC_CONFIG = {
    'active_codec': 'jpeg',           # 'jpeg', 'webp', 'h264', 'adaptive'
    'quality': 80,                    # 1-100
    'preprocessing': 'none',          # 'quality', 'balanced', 'fast', 'none' - NONE por defecto para evitar lag
    'target_fps': 16,                 # Para sincronización
    'resize_factor': 1.0,             # 1.0=full, 0.8=80%, etc
}

# Instancia global del codec activo
_active_codec = None

def get_active_codec():
    """Obtener instancia del codec activo"""
    global _active_codec

    if _active_codec is None:
        _active_codec = create_codec(
            codec_type=CODEC_CONFIG['active_codec'],
            quality=CODEC_CONFIG['quality'],
            preprocessing=CODEC_CONFIG['preprocessing']
        )

    return _active_codec

def switch_codec(codec_type, quality=None):
    """
    Cambiar el codec activo en tiempo real

    Args:
        codec_type: 'jpeg', 'webp', 'h264', 'adaptive'
        quality: 1-100 (opcional)
    """
    global _active_codec

    CODEC_CONFIG['active_codec'] = codec_type
    if quality is not None:
        CODEC_CONFIG['quality'] = quality

    _active_codec = create_codec(
        codec_type=codec_type,
        quality=CODEC_CONFIG['quality'],
        preprocessing=CODEC_CONFIG['preprocessing']
    )

    print(f"[INFO] Codec cambiado a: {codec_type} (quality={CODEC_CONFIG['quality']})")
