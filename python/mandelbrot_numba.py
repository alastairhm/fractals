"""
Numba-accelerated Mandelbrot renderer.

pip install numba pillow numpy
"""

import numpy as np
from numba import njit, prange
from PIL import Image

WIDTH, HEIGHT = 1920, 1080
MAX_ITER = 500

# Default full-set view
CENTER_X, CENTER_Y = -0.5, 0.0
ZOOM = 1.5  # half-height of the view in the complex plane


@njit(parallel=True, fastmath=True, cache=True)
def mandelbrot(width, height, cx, cy, zoom, max_iter):
    aspect = width / height
    x_min, x_max = cx - zoom * aspect, cx + zoom * aspect
    y_min, y_max = cy - zoom, cy + zoom

    escape = np.zeros((height, width), dtype=np.float64)

    for row in prange(height):
        y = y_min + (y_max - y_min) * row / (height - 1)
        for col in range(width):
            x = x_min + (x_max - x_min) * col / (width - 1)

            zr, zi = 0.0, 0.0
            i = 0
            while zr * zr + zi * zi <= 4.0 and i < max_iter:
                zr, zi = zr * zr - zi * zi + x, 2.0 * zr * zi + y
                i += 1

            if i == max_iter:
                escape[row, col] = 0.0  # inside the set -> stays black
            else:
                # smooth (continuous) iteration count to avoid banding
                log_zn = np.log(zr * zr + zi * zi) / 2.0
                nu = np.log(log_zn / np.log(2.0)) / np.log(2.0)
                escape[row, col] = i + 1 - nu

    return escape


def colorize(escape, max_iter):
    """Map smooth escape values to an RGB image using a simple gradient."""
    norm = np.clip(escape / max_iter, 0, 1)

    # simple periodic gradient for that swirly banded-but-smooth look
    r = (0.5 + 0.5 * np.cos(6.28318 * (norm * 3.0 + 0.0))) * 255
    g = (0.5 + 0.5 * np.cos(6.28318 * (norm * 3.0 + 0.33))) * 255
    b = (0.5 + 0.5 * np.cos(6.28318 * (norm * 3.0 + 0.67))) * 255

    rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
    rgb[escape == 0] = [0, 0, 0]  # points inside the set: pure black
    return rgb


if __name__ == "__main__":
    print("Rendering...")
    escape = mandelbrot(WIDTH, HEIGHT, CENTER_X, CENTER_Y, ZOOM, MAX_ITER)

    img = Image.fromarray(colorize(escape, MAX_ITER), mode="RGB")
    img.save("mandelbrot.png")
    print("Saved mandelbrot.png")
