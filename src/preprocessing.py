"""
Preprocessing: Filtros y mejoras de imagen
Módulo modular para aplicar transformaciones pre-encoding
"""

import cv2
import numpy as np


class ImagePreprocessor:
    """
    Cadena de filtros aplicables al video.
    Cada método retorna el frame modificado.
    """

    @staticmethod
    def denoise(frame, h=10, template_size=7, search_size=21):
        """
        Reducción de ruido (Bilateral Filter + NLM)

        Args:
            frame: imagen BGR
            h: fuerza del denoise (default 10)
            template_size: tamaño ventana de template
            search_size: tamaño ventana de búsqueda

        Returns:
            frame denoised
        """
        # Bilateral filter: suaviza sin perder bordes
        frame = cv2.bilateralFilter(frame, 9, h, h)
        return frame

    @staticmethod
    def enhance_contrast(frame, clip_limit=3.0, tile_size=8):
        """
        Aumento de contraste con CLAHE (Contrast Limited Adaptive Histogram Equalization)

        Args:
            frame: imagen BGR
            clip_limit: límite de amplificación (default 3.0)
            tile_size: tamaño del tile para CLAHE

        Returns:
            frame con contraste mejorado
        """
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
        l = clahe.apply(l)

        frame = cv2.merge([l, a, b])
        frame = cv2.cvtColor(frame, cv2.COLOR_LAB2BGR)

        return frame

    @staticmethod
    def sharpen(frame, strength=1.5):
        """
        Nitidez (Unsharp Mask)

        Args:
            frame: imagen BGR
            strength: factor de nitidez (default 1.5)

        Returns:
            frame sharpened
        """
        gaussian = cv2.GaussianBlur(frame, (0, 0), 2.0)
        frame = cv2.addWeighted(frame, 1.0 + strength, gaussian, -strength, 0)
        frame = np.clip(frame, 0, 255).astype(np.uint8)

        return frame

    @staticmethod
    def brightness_contrast(frame, brightness=0, contrast=1.0):
        """
        Ajuste de brillo y contraste

        Args:
            frame: imagen BGR
            brightness: -100 a +100
            contrast: 0.5 a 2.0 (1.0 = sin cambio)

        Returns:
            frame ajustado
        """
        frame = np.float32(frame) / 255.0
        frame = frame * contrast + brightness / 255.0
        frame = np.clip(frame, 0, 1) * 255
        frame = np.uint8(frame)

        return frame

    @staticmethod
    def color_correction(frame, saturation=1.0):
        """
        Ajuste de saturación de color

        Args:
            frame: imagen BGR
            saturation: 0.0 a 2.0 (1.0 = sin cambio)

        Returns:
            frame con saturación ajustada
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hsv = hsv.astype(np.float32)
        hsv[:, :, 1] = hsv[:, :, 1] * saturation
        hsv = np.clip(hsv, 0, 255).astype(np.uint8)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        return frame

    @staticmethod
    def resize(frame, scale_factor=1.0):
        """
        Redimensionar imagen

        Args:
            frame: imagen BGR
            scale_factor: 0.5 = mitad, 1.0 = original

        Returns:
            frame redimensionado
        """
        if scale_factor == 1.0:
            return frame

        h, w = frame.shape[:2]
        new_w = int(w * scale_factor)
        new_h = int(h * scale_factor)

        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        return frame

    @staticmethod
    def adaptive_histogram(frame):
        """
        Equalización adaptativa (CLAHE en escala de grises convertida a color)

        Args:
            frame: imagen BGR

        Returns:
            frame con histograma equalizado
        """
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)

        frame = cv2.merge([l, a, b])
        frame = cv2.cvtColor(frame, cv2.COLOR_LAB2BGR)

        return frame


class PreprocessingPipeline:
    """
    Cadena de procesamiento: aplica múltiples filtros en secuencia
    """

    def __init__(self):
        self.filters = []

    def add_denoise(self, h=10):
        """Agregar filtro de denoise"""
        self.filters.append(('denoise', {'h': h}))
        return self

    def add_contrast(self, clip_limit=3.0):
        """Agregar filtro de contraste"""
        self.filters.append(('contrast', {'clip_limit': clip_limit}))
        return self

    def add_sharpen(self, strength=1.5):
        """Agregar filtro de nitidez"""
        self.filters.append(('sharpen', {'strength': strength}))
        return self

    def add_brightness(self, brightness=0, contrast=1.0):
        """Agregar ajuste de brillo"""
        self.filters.append(('brightness', {'brightness': brightness, 'contrast': contrast}))
        return self

    def add_resize(self, scale_factor=1.0):
        """Agregar redimensionamiento"""
        self.filters.append(('resize', {'scale_factor': scale_factor}))
        return self

    def add_saturation(self, saturation=1.0):
        """Agregar ajuste de saturación"""
        self.filters.append(('saturation', {'saturation': saturation}))
        return self

    def process(self, frame):
        """
        Aplicar toda la cadena de filtros al frame

        Args:
            frame: imagen BGR

        Returns:
            frame procesado
        """
        result = frame.copy()

        for filter_name, params in self.filters:
            if filter_name == 'denoise':
                result = ImagePreprocessor.denoise(result, **params)
            elif filter_name == 'contrast':
                result = ImagePreprocessor.enhance_contrast(result, **params)
            elif filter_name == 'sharpen':
                result = ImagePreprocessor.sharpen(result, **params)
            elif filter_name == 'brightness':
                result = ImagePreprocessor.brightness_contrast(result, **params)
            elif filter_name == 'resize':
                result = ImagePreprocessor.resize(result, **params)
            elif filter_name == 'saturation':
                result = ImagePreprocessor.color_correction(result, **params)

        return result

    def clear(self):
        """Limpiar la cadena de filtros"""
        self.filters = []
        return self


# Presets profesionales listos para usar
PRESETS = {
    'quality': PreprocessingPipeline()
        .add_denoise(h=10)
        .add_contrast(clip_limit=3.0)
        .add_sharpen(strength=1.5)
        .add_saturation(saturation=1.1),

    'balanced': PreprocessingPipeline()
        .add_denoise(h=8)
        .add_contrast(clip_limit=2.5)
        .add_sharpen(strength=1.0),

    'fast': PreprocessingPipeline()
        .add_resize(scale_factor=0.8),

    'none': PreprocessingPipeline(),
}
