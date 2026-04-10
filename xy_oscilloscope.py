"""
Terminal XY Oscilloscope - Live Desktop Audio
Uses WASAPI loopback (via pyaudiowpatch) to capture system audio.
Plots Left channel on X, Right channel on Y as a Lissajous figure.
Braille-character rendering with phosphor bloom, CRT scanlines, and vignette.
"""

import sys
import os
import time
import threading
import math
import numpy as np
import pyaudiowpatch as pyaudio
import shutil

# ── Braille rendering ────────────────────────────────────────────────
BRAILLE_BASE = 0x2800
DOT_MAP = [
    [0x01, 0x08],
    [0x02, 0x10],
    [0x04, 0x20],
    [0x40, 0x80],
]


class BrailleCanvas:
    def __init__(self, char_w, char_h):
        self.char_w = char_w
        self.char_h = char_h
        self.px_w = char_w * 2
        self.px_h = char_h * 4
        self.grid = np.zeros((char_h, char_w), dtype=np.uint8)

    def clear(self):
        self.grid[:] = 0

    def set(self, px, py):
        if 0 <= px < self.px_w and 0 <= py < self.px_h:
            cx, rx = divmod(px, 2)
            cy, ry = divmod(py, 4)
            self.grid[cy, cx] |= DOT_MAP[ry][rx]

    def set_batch(self, pxs, pys):
        """Set multiple pixels at once using numpy vectorization."""
        mask = (pxs >= 0) & (pxs < self.px_w) & (pys >= 0) & (pys < self.px_h)
        pxs = pxs[mask]
        pys = pys[mask]
        cx, rx = np.divmod(pxs, 2)
        cy, ry = np.divmod(pys, 4)
        dot_values = np.array(DOT_MAP, dtype=np.uint8)
        dots = dot_values[ry, rx]
        np.bitwise_or.at(self.grid, (cy.astype(int), cx.astype(int)), dots)

    def render(self):
        lines = []
        for row in self.grid:
            lines.append("".join(chr(BRAILLE_BASE + int(b)) for b in row))
        return lines


# ── CRT phosphor colour (24-bit true colour) ────────────────────────
def crt_colour(intensity, scanline_dim=1.0):
    """
    Phosphor green CRT glow using 24-bit truecolour.
    Low intensity  = deep blue-green shadow
    Mid intensity  = vivid electric green
    High intensity = white-hot bloom with cyan fringe
    scanline_dim   = per-row brightness modulation (CRT scanline effect)
    """
    t = max(0.0, min(1.0, intensity)) * scanline_dim

    # Gamma curve to push more of the range into the bright end (CRT phosphor response)
    t = t ** 0.7

    if t < 0.15:
        # Dark: near-black to deep teal
        s = t / 0.15
        r, g, b = int(2 * s), int(18 * s), int(28 * s)
    elif t < 0.4:
        # Low-mid: teal to electric green
        s = (t - 0.15) / 0.25
        r = int(2 + 8 * s)
        g = int(18 + 200 * (s ** 0.8))
        b = int(28 + 40 * s - 30 * s * s)
    elif t < 0.7:
        # Mid-high: electric green with rising brightness
        s = (t - 0.4) / 0.3
        r = int(10 + 80 * s)
        g = int(218 + 37 * s)
        b = int(38 + 80 * s)
    elif t < 0.9:
        # Hot: green-white bloom
        s = (t - 0.7) / 0.2
        r = int(90 + 130 * s)
        g = 255
        b = int(118 + 100 * s)
    else:
        # White-hot center
        s = (t - 0.9) / 0.1
        r = int(220 + 35 * s)
        g = 255
        b = int(218 + 37 * s)

    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f"\033[38;2;{r};{g};{b}m"


def crt_bg_colour(intensity):
    """Faint background glow for bloom effect."""
    t = max(0.0, min(1.0, intensity))
    if t < 0.3:
        return ""
    s = (t - 0.3) / 0.7
    r = int(2 * s)
    g = int(15 * s)
    b = int(8 * s)
    return f"\033[48;2;{r};{g};{b}m"


# ── Pre-compute colour LUT for fast rendering ──────────────────────────
def build_color_lut(levels=128):
    """Pre-compute colour strings for each intensity level to avoid per-char recomputation."""
    lut = []
    for i in range(levels):
        t = i / (levels - 1) if levels > 1 else 0
        fg_full = crt_colour(t, 1.0)
        fg_dim = crt_colour(t, 0.72)
        bg = crt_bg_colour(t * 0.5)
        lut.append((fg_full, fg_dim, bg))
    return lut


COLOR_LUT = build_color_lut(128)


# ── Precompute vignette mask ─────────────────────────────────────────
def make_vignette(char_w, char_h):
    """Radial darkening from center, simulating CRT curvature."""
    vy = np.linspace(-1, 1, char_h)
    vx = np.linspace(-1, 1, char_w)
    vxx, vyy = np.meshgrid(vx, vy)
    dist = np.sqrt(vxx**2 + vyy**2)
    # Smooth falloff: full brightness in center, dims toward edges
    vignette = 1.0 - 0.45 * np.clip(dist - 0.3, 0, None) ** 1.5
    return np.clip(vignette, 0.15, 1.0).astype(np.float32)


RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
WHITE = "\033[97m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


# ── Audio state ──────────────────────────────────────────────────────
class AudioState:
    def __init__(self, buf_size=8192):
        self.lock = threading.Lock()
        self.left = np.zeros(buf_size, dtype=np.float32)
        self.right = np.zeros(buf_size, dtype=np.float32)
        self.peak_l = 0.0
        self.peak_r = 0.0
        self.buf_size = buf_size

    def push(self, left, right):
        with self.lock:
            n = len(left)
            self.left = np.roll(self.left, -n)
            self.right = np.roll(self.right, -n)
            self.left[-n:] = left
            self.right[-n:] = right
            self.peak_l = max(self.peak_l * 0.95, np.max(np.abs(left)))
            self.peak_r = max(self.peak_r * 0.95, np.max(np.abs(right)))

    def snapshot(self):
        with self.lock:
            return self.left.copy(), self.right.copy(), self.peak_l, self.peak_r


# ── Find WASAPI loopback device ─────────────────────────────────────
def find_loopback_device(p):
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        return None, "WASAPI host API not available"

    default_output_idx = wasapi_info["defaultOutputDevice"]
    default_output = p.get_device_info_by_index(default_output_idx)

    for loopback in p.get_loopback_device_info_generator():
        if default_output["name"] in loopback["name"]:
            return loopback, loopback["name"]

    for loopback in p.get_loopback_device_info_generator():
        return loopback, loopback["name"]

    return None, "No loopback devices found"


# ── Bloom: gaussian-ish spread on the persistence buffer ─────────────
def apply_bloom(buf, strength=0.12):
    """Cheap 2-pass box blur to simulate phosphor bloom / halation."""
    h, w = buf.shape
    bloomed = buf.copy()
    # Horizontal pass
    bloomed[:, 1:] = np.maximum(bloomed[:, 1:], buf[:, :-1] * strength)
    bloomed[:, :-1] = np.maximum(bloomed[:, :-1], buf[:, 1:] * strength)
    # Vertical pass
    bloomed[1:, :] = np.maximum(bloomed[1:, :], buf[:-1, :] * strength * 0.7)
    bloomed[:-1, :] = np.maximum(bloomed[:-1, :], buf[1:, :] * strength * 0.7)
    # Diagonal bleed (faint)
    d = strength * 0.4
    bloomed[1:, 1:] = np.maximum(bloomed[1:, 1:], buf[:-1, :-1] * d)
    bloomed[:-1, 1:] = np.maximum(bloomed[:-1, 1:], buf[1:, :-1] * d)
    bloomed[1:, :-1] = np.maximum(bloomed[1:, :-1], buf[:-1, 1:] * d)
    bloomed[:-1, :-1] = np.maximum(bloomed[:-1, :-1], buf[1:, 1:] * d)
    return bloomed


# ── Bresenham line drawing for sample interpolation ──────────────────
def draw_line(buf, x0, y0, x1, y1, h, w):
    """Draw an anti-aliased-ish line between two sample points."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        if 0 <= x0 < w and 0 <= y0 < h:
            buf[y0, x0] = 1.0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


# ── Draw XY scope ───────────────────────────────────────────────────
def draw_frame(state, canvas, term_w, term_h, device_name, fps, gain, decay,
               persistence_buf, vignette, show_help, frame_num,
               sharp_mode=False, subsample=1, bloom_strength=0.15, target_fps=60):
    canvas.clear()
    left, right, peak_l, peak_r = state.snapshot()

    # Auto-gain normalisation
    peak = max(peak_l, peak_r, 1e-6)
    scale = gain / peak

    # Map samples to pixel coords (centre = origin)
    cx, cy = canvas.px_w / 2, canvas.px_h / 2
    xs = (left * scale * cx * 0.92 + cx).astype(int)
    ys = (cy - right * scale * cy * 0.92).astype(int)

    # Decay old persistence buffer (multi-rate: fast decay + slow ghost)
    persistence_buf *= decay

    h, w = persistence_buf.shape

    if sharp_mode:
        # Point mode: plot samples directly for crisp dots
        valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        persistence_buf[ys[valid], xs[valid]] = 1.0
    else:
        # Draw lines between consecutive samples (subsampled for speed)
        step = max(1, subsample)
        for i in range(0, len(xs) - 1, step):
            draw_line(persistence_buf, xs[i], ys[i], xs[i + 1], ys[i + 1], h, w)

    # Apply phosphor bloom (skip in sharp mode for cleaner output)
    if sharp_mode:
        display_buf = persistence_buf.copy()
    else:
        display_buf = apply_bloom(persistence_buf, strength=bloom_strength)

    # Render into canvas (vectorized batch)
    active_y, active_x = np.where(display_buf > 0.008)
    intensities = display_buf[active_y, active_x]

    canvas.set_batch(active_x, active_y)

    lines = canvas.render()

    # Per-character intensity (vectorized with np.maximum.at)
    char_intensity = np.zeros((canvas.char_h, canvas.char_w), dtype=np.float32)
    cx_all = active_x // 2
    cy_all = active_y // 4
    valid = (cx_all < canvas.char_w) & (cy_all < canvas.char_h)
    np.maximum.at(char_intensity, (cy_all[valid], cx_all[valid]), intensities[valid])

    # Apply vignette
    char_intensity *= vignette

    # ── Build coloured output with CRT effects (LUT-accelerated) ──
    coloured_lines = []
    lut_size = len(COLOR_LUT)
    empty_odd = "\033[38;2;3;8;5m "
    empty_even = "\033[38;2;5;12;8m\u00b7"
    braille_empty = chr(BRAILLE_BASE)
    for row_idx, line in enumerate(lines):
        is_odd = row_idx % 2 == 1
        scanline_idx = 1 if is_odd else 0
        empty_ch = empty_odd if is_odd else empty_even

        parts = []
        ci_row = char_intensity[row_idx]
        for col_idx, ch in enumerate(line):
            if ch != braille_empty:
                li = min(int(ci_row[col_idx] * (lut_size - 1)), lut_size - 1)
                parts.append(f"{COLOR_LUT[li][scanline_idx]}{COLOR_LUT[li][2]}{ch}")
            else:
                parts.append(empty_ch)
        coloured_lines.append("".join(parts) + RESET)

    # ── Compose frame ────────────────────────────────────────────
    buf = ["\033[H"]  # cursor home

    # Title bar - CRT style
    title = f" {BOLD}\033[38;2;0;255;120m\u2588\u2588 XY OSCILLOSCOPE{RESET}"
    status = f"\033[38;2;0;180;80m{device_name[:38]}{RESET}  {DIM}|{RESET}  \033[38;2;0;200;100m{fps:.0f} fps{RESET}  "
    pad = term_w - 22 - min(len(device_name), 38) - 14
    buf.append(title + " " * max(pad, 1) + status)

    # Separator - CRT bezel edge
    bezel = "\033[38;2;20;50;30m"
    buf.append(f"{bezel}{'━' * term_w}{RESET}")

    # Scope area
    scope_w = canvas.char_w
    left_pad = max((term_w - scope_w - 6) // 2, 0)
    margin = " " * left_pad

    # Top axis label
    axis_col = "\033[38;2;0;80;50m"
    buf.append(margin + "   " + " " * (scope_w // 2) + f"{axis_col}+R{RESET}")

    for i, line in enumerate(coloured_lines):
        prefix = f"{axis_col}-L{RESET} " if i == len(coloured_lines) // 2 else "   "
        suffix = f" {axis_col}+L{RESET}" if i == len(coloured_lines) // 2 else ""
        buf.append(margin + prefix + line + suffix)

    buf.append(margin + "   " + " " * (scope_w // 2) + f"{axis_col}-R{RESET}")
    buf.append(f"{bezel}{'━' * term_w}{RESET}")

    # Level meters with CRT phosphor colours
    meter_w = min(term_w - 20, 40)
    lbar = max(0, min(int(peak_l * scale * meter_w), meter_w))
    rbar = max(0, min(int(peak_r * scale * meter_w), meter_w))

    def meter_bar(filled, total):
        segs = []
        for i in range(total):
            if i < filled:
                t = i / total
                if t < 0.6:
                    segs.append(f"\033[38;2;0;{int(150+105*t)};{int(60*t)}m\u2588")
                elif t < 0.85:
                    segs.append(f"\033[38;2;{int(200*(t-0.6)/0.25)};255;0m\u2588")
                else:
                    segs.append(f"\033[38;2;255;{int(255-200*(t-0.85)/0.15)};0m\u2588")
            else:
                segs.append(f"\033[38;2;10;25;15m\u2591")
        return "".join(segs)

    buf.append(
        f"  {WHITE}L{RESET} {meter_bar(lbar, meter_w)}{RESET}"
        f"   {WHITE}R{RESET} {meter_bar(rbar, meter_w)}{RESET}"
    )

    # Controls bar
    ctrl_col = "\033[38;2;0;100;60m"
    if show_help:
        sharp_str = "ON" if sharp_mode else "OFF"
        buf.append(f"  {ctrl_col}[+/-] gain:{gain:.1f}  [d/D] decay:{decay:.2f}  [b/B] bloom  [s] sharp:{sharp_str}  [f/F] fps:{target_fps}  [h] help  [q] quit{RESET}")
    else:
        buf.append(f"  {ctrl_col}[h] help  [q] quit{RESET}")

    # Pad remaining lines (CRT dark background)
    used = len(buf)
    for _ in range(term_h - used):
        buf.append(" " * term_w)

    sys.stdout.write("\n".join(buf))
    sys.stdout.flush()


# ── Main ─────────────────────────────────────────────────────────────
def main():
    print(f"{CYAN}XY Oscilloscope{RESET} - scanning for WASAPI loopback device...")

    p = pyaudio.PyAudio()
    loopback_dev, dev_name = find_loopback_device(p)

    if loopback_dev is None:
        print(f"\n{YELLOW}Could not find a loopback device.{RESET}")
        print(f"Reason: {dev_name}\n")
        print("Available loopback devices:")
        try:
            for lb in p.get_loopback_device_info_generator():
                print(f"  [{lb['index']}] {lb['name']}  "
                      f"(ch={lb['maxInputChannels']}, rate={lb['defaultSampleRate']:.0f})")
        except Exception:
            print("  (none found)")
        print(f"\nRe-run with:  python {sys.argv[0]} <device_index>")
        p.terminate()
        sys.exit(1)

    if len(sys.argv) > 1:
        idx = int(sys.argv[1])
        loopback_dev = p.get_device_info_by_index(idx)
        dev_name = loopback_dev["name"]

    channels = int(loopback_dev["maxInputChannels"])
    sample_rate = int(loopback_dev["defaultSampleRate"])
    dev_index = loopback_dev["index"]

    print(f"Using: {GREEN}{dev_name}{RESET} (index {dev_index}, {channels}ch, {sample_rate}Hz)")

    # Bigger audio buffer for higher resolution traces
    audio = AudioState(buf_size=8192)

    def audio_callback(in_data, frame_count, time_info, status):
        samples = np.frombuffer(in_data, dtype=np.float32)
        if channels >= 2:
            left = samples[0::channels]
            right = samples[1::channels]
        else:
            left = samples
            right = samples
        audio.push(left, right)
        return (None, pyaudio.paContinue)

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=channels,
        rate=sample_rate,
        input=True,
        input_device_index=dev_index,
        frames_per_buffer=2048,  # larger buffer for smoother capture
        stream_callback=audio_callback,
    )

    # Terminal setup
    if sys.platform == "win32":
        os.system("")  # enable ANSI + truecolour on Windows
        import msvcrt
    else:
        import tty, termios
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    term_size = shutil.get_terminal_size()
    term_w = term_size.columns
    term_h = term_size.lines
    # Use almost the full terminal for maximum resolution
    canvas_w = min(term_w - 8, 200)
    canvas_h = min(term_h - 9, 60)
    canvas = BrailleCanvas(canvas_w, canvas_h)

    persistence_buf = np.zeros((canvas.px_h, canvas.px_w), dtype=np.float32)
    vignette = make_vignette(canvas.char_w, canvas.char_h)

    gain = 1.0
    decay = 0.88
    show_help = True
    bloom_strength = 0.15
    sharp_mode = False
    target_fps = 60
    subsample = 1
    running = True

    sys.stdout.write(HIDE_CURSOR)
    sys.stdout.write("\033[2J")
    sys.stdout.flush()

    def check_key():
        if sys.platform == "win32":
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b'\xe0', b'\x00'):
                    msvcrt.getch()
                    return None
                return ch.decode("utf-8", errors="ignore")
        else:
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                return sys.stdin.read(1)
        return None

    try:
        stream.start_stream()
        frame_count = 0
        frame_num = 0
        t0 = time.perf_counter()
        fps = 0.0

        while running:
            key = check_key()
            if key:
                if key in ("q", "Q", "\x03"):
                    running = False
                    break
                elif key == "+":
                    gain = min(gain + 0.2, 10.0)
                elif key == "-":
                    gain = max(gain - 0.2, 0.2)
                elif key == "d":
                    decay = min(decay + 0.02, 0.99)
                elif key == "D":
                    decay = max(decay - 0.02, 0.5)
                elif key == "b":
                    bloom_strength = min(bloom_strength + 0.03, 0.5)
                elif key == "B":
                    bloom_strength = max(bloom_strength - 0.03, 0.0)
                elif key == "s":
                    sharp_mode = not sharp_mode
                elif key == "f":
                    target_fps = min(target_fps + 10, 144)
                elif key == "F":
                    target_fps = max(target_fps - 10, 10)
                elif key == "r":
                    subsample = max(subsample - 1, 1)
                elif key == "R":
                    subsample = min(subsample + 2, 16)
                elif key == "h":
                    show_help = not show_help

            new_size = shutil.get_terminal_size()
            if new_size != term_size:
                term_size = new_size
                term_w = term_size.columns
                term_h = term_size.lines
                canvas_w = min(term_w - 8, 200)
                canvas_h = min(term_h - 9, 60)
                canvas = BrailleCanvas(canvas_w, canvas_h)
                persistence_buf = np.zeros((canvas.px_h, canvas.px_w), dtype=np.float32)
                vignette = make_vignette(canvas.char_w, canvas.char_h)
                sys.stdout.write("\033[2J")

            draw_frame(audio, canvas, term_w, term_h, dev_name, fps, gain,
                       decay, persistence_buf, vignette, show_help, frame_num,
                       sharp_mode, subsample, bloom_strength, target_fps)

            frame_count += 1
            frame_num += 1
            elapsed = time.perf_counter() - t0
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                t0 = time.perf_counter()

            time.sleep(1 / target_fps)

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        if sys.platform != "win32":
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        print(f"{CYAN}Oscilloscope closed.{RESET}")


if __name__ == "__main__":
    main()
