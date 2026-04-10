========================================
=      XY OSCILLOSCOPE - LIVE AUDIO     =
========================================

Welcome to the `xy_oscilloscope` project!
This repo captures your desktop audio using WASAPI loopback,
then plots the left and right channels as a live Lissajous figure
using styled braille graphics in the terminal.

────────────────────────────────────────
What this repo includes:
────────────────────────────────────────
- `xy_oscilloscope.py` : Terminal-based real-time audio visualizer
- `requirements.txt`  : Required Python packages for playback and rendering

Animated vibe:

      .--.        .--.        .--.        .--.
    .'_\/_'.    .'_\/_'.    .'_\/_'.    .'_\/_'.
    '. /\ .'    '. /\ .'    '. /\ .'    '. /\ .'
      "||"        "||"        "||"        "||"
      /__\        /__\        /__\        /__\

────────────────────────────────────────
Dependencies:
────────────────────────────────────────
- numpy
- pyaudiowpatch

Install them with:

    pip install -r requirements.txt

────────────────────────────────────────
How to run:
────────────────────────────────────────
1) Make sure your terminal supports 24-bit colors and braille characters.
2) Run the script:

    python xy_oscilloscope.py

3) Enjoy the glowing CRT-style Lissajous display.

────────────────────────────────────────
Notes:
────────────────────────────────────────
- The script uses WASAPI loopback, so it captures system audio output.
- It paints each frame with a CRT phosphor glow, scanlines, and vignette.
- Adjust your terminal size for best results.

────────────────────────────────────────
Repo Info:
────────────────────────────────────────
This repository was created and published automatically to GitHub.
Visit:
https://github.com/SomberHighs/xy_oscilloscope

────────────────────────────────────────
Thanks for checking it out!
Keep the waves alive.
