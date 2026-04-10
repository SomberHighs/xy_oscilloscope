"""Raw interactive demo for the xy_oscilloscope GitHub repository."""

import math
import os
import sys
import time

try:
    import numpy as np
except ImportError:
    print("Error: numpy is required for the interactive demo.")
    print("Install with: pip install numpy")
    sys.exit(1)

BRAILLE_BASE = 0x2800
DOT_MAP = [
    [0x01, 0x08],
    [0x02, 0x10],
    [0x04, 0x20],
    [0x40, 0x80],
]

GREEN = "\033[38;2;110;255;120m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"


def make_canvas(width, height):
    return np.zeros((height, width), dtype=np.uint8)


def set_pixel(canvas, x, y):
    height, width = canvas.shape
    if 0 <= x < width * 2 and 0 <= y < height * 4:
        cx, rx = divmod(x, 2)
        cy, ry = divmod(y, 4)
        canvas[cy, cx] |= DOT_MAP[ry][rx]


def render_canvas(canvas):
    lines = []
    for row in canvas:
        line = "".join(chr(BRAILLE_BASE + int(val)) for val in row)
        lines.append(line)
    return "\n".join(lines)


def generate_lissajous(width, height, frames, fx, fy, phase, speed):
    t = np.linspace(0, 2 * math.pi, frames)
    x = np.sin(fx * t + phase)
    y = np.sin(fy * t)
    x = ((x + 1.0) / 2.0) * (width * 2 - 1)
    y = ((y + 1.0) / 2.0) * (height * 4 - 1)
    return x.astype(np.int32), y.astype(np.int32)


def demo_pattern(name, width, height, frames):
    if name == "circle":
        return generate_lissajous(width, height, frames, 1, 1, 0, 1)
    if name == "figure8":
        return generate_lissajous(width, height, frames, 2, 1, 0, 1)
    if name == "spiro":
        return generate_lissajous(width, height, frames, 5, 4, math.pi / 2, 1)
    if name == "random":
        x = np.random.rand(frames) * (width * 2 - 1)
        y = np.random.rand(frames) * (height * 4 - 1)
        return x.astype(np.int32), y.astype(np.int32)
    return generate_lissajous(width, height, frames, 3, 2, math.pi / 3, 1)


def run_demo():
    width, height = 40, 12
    intro = (
        "Raw Interactive Demo for xy_oscilloscope\n"
        "--------------------------------------\n"
        "This demo shows a terminal braille oscilloscope effect without audio.\n"
    )
    print(intro)

    choices = {
        "1": "circle",
        "2": "figure8",
        "3": "spiro",
        "4": "random",
    }
    for key, name in choices.items():
        print(f"{key}) {name}")

    choice = input("Choose a demo pattern [1-4]: ").strip() or "1"
    pattern = choices.get(choice, "circle")
    frames = 120
    speed = 0.04

    print(f"\nRendering raw interactive demo: {pattern}\nPress Ctrl+C to exit anytime.\n")
    time.sleep(0.8)

    x, y = demo_pattern(pattern, width, height, frames)
    frame_idx = 0
    try:
        while True:
            canvas = make_canvas(width, height)
            idx = frame_idx % frames
            set_pixel(canvas, x[idx], y[idx])
            output = render_canvas(canvas)
            print(CLEAR + GREEN + output + RESET)
            frame_idx += 1
            time.sleep(speed)
    except KeyboardInterrupt:
        print(RESET + "\nDemo ended. Thank you for trying the raw interactive preview!\n")


if __name__ == "__main__":
    run_demo()
