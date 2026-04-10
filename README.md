# xy_oscilloscope

> A terminal audio oscilloscope that captures desktop sound via WASAPI and renders live Lissajous figures in braille.

---

## 🚀 What this project does

- Captures system audio using `pyaudiowpatch` and Windows WASAPI loopback.
- Plots the left audio channel on X and the right channel on Y.
- Renders live output as styled braille characters in the terminal.
- Applies CRT-inspired effects: phosphor glow, scanlines, vignette, and color bloom.

---

## 📦 Files included

- `xy_oscilloscope.py` — main real-time audio visualizer script.
- `requirements.txt` — Python dependencies used by the project.
- `README.txt` — legacy animated plain-text project description.

---

## 🛠️ Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

---

## ▶️ Run

```bash
python xy_oscilloscope.py
```

Make sure your terminal supports:

- 24-bit color sequences
- Unicode braille block characters
- ANSI escape codes

---

## ✨ Features

- **Live desktop audio capture** via WASAPI loopback
- **Braille-based rendering** for high-density terminal pixels
- **CRT-style visual effects** for a retro synthwave aesthetic
- **Optimized draw loop** with precomputed color LUT

---

## 🎛️ Notes

- Best results are produced in a wide terminal with a dark theme.
- If the audio capture fails, ensure the default output device is available and that WASAPI is supported.
- The visualizer is designed for Windows terminals.

---

## 🎉 Example output

```
┌─────────────────────────────────────────────┐
|   •   •   •   •   •   •   •   •   •   •     |
|      █ ▄ ▂ ▄ ░ ░ ▒ ▒ ▒ ░ ░ ▄ ▂ ▄ █          |
|   •   •   •   •   •   •   •   •   •   •     |
└─────────────────────────────────────────────┘
```

---

## 📍 Repository

Published to GitHub at:

https://github.com/SomberHighs/xy_oscilloscope

---

## 💡 Want more?

If you'd like, I can also add:

- a proper `.gitignore`
- a `setup.py` / `pyproject.toml`
- a `README` badge section for installation and usage
