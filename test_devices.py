"""
Device Monitor — Verify Muse 2 and/or ESP32 ECG without harmonic_shaper.

Listens for EEG (/muse/eeg) and ECG (/ecg/raw) data and shows a live
terminal dashboard with signal quality, band powers, heart rate, and
ASCII traces. No harmonic_shaper, no muse_bridge needed.

Usage:
    python test_devices.py                  # monitor both on default ports
    python test_devices.py --eeg            # EEG only (Muse 2 / Mind Monitor)
    python test_devices.py --ecg            # ECG only (ESP32 + AD8232)
    python test_devices.py --eeg-port 5000  # custom EEG listen port
    python test_devices.py --ecg-port 5001  # custom ECG listen port
"""

import argparse
import signal
import sys
import time
import threading
import numpy as np
from pythonosc import dispatcher, osc_server

# ─────────────────────────────────────────────
# EEG State
# ─────────────────────────────────────────────

CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
BANDS = {"delta": (0.5, 4), "theta": (4, 8), "alpha": (8, 13),
         "beta": (13, 30), "gamma": (30, 44)}

eeg_buffers = {ch: [] for ch in CHANNELS}
eeg_contact = {ch: 4.0 for ch in CHANNELS}  # 1=good, 4=off
eeg_packets = 0
eeg_start = None
eeg_band_powers = {}
SFREQ = 256
WINDOW = SFREQ * 2  # 2 seconds of data

# ─────────────────────────────────────────────
# ECG State
# ─────────────────────────────────────────────

ecg_packets = 0
ecg_samples = 0
ecg_start = None
ecg_leads_off = True
ecg_trace = []
ECG_TRACE_WIDTH = 50

# R-peak detection
ecg_detector = None
ecg_beats = 0
ecg_bpm = 0.0
ecg_rr = 0.0

# ─────────────────────────────────────────────
# OSC Handlers
# ─────────────────────────────────────────────

def eeg_handler(address, *args):
    global eeg_packets, eeg_start
    if eeg_start is None:
        eeg_start = time.monotonic()
    eeg_packets += 1
    for i, ch in enumerate(CHANNELS):
        if i < len(args):
            eeg_buffers[ch].append(float(args[i]))
            if len(eeg_buffers[ch]) > WINDOW:
                eeg_buffers[ch].pop(0)


def horseshoe_handler(address, *args):
    for i, ch in enumerate(CHANNELS):
        if i < len(args):
            eeg_contact[ch] = float(args[i])


def ecg_raw_handler(address, *args):
    global ecg_packets, ecg_samples, ecg_start, ecg_beats, ecg_bpm, ecg_rr
    if ecg_start is None:
        ecg_start = time.monotonic()
    ecg_packets += 1
    ecg_samples += len(args)

    # Feed trace
    if args:
        ecg_trace.append(float(args[len(args) // 2]))
        if len(ecg_trace) > ECG_TRACE_WIDTH:
            ecg_trace.pop(0)

    # R-peak detection
    if ecg_detector is not None:
        beats = ecg_detector.add_samples(list(args))
        for bpm, rr_ms in beats:
            ecg_beats += 1
            ecg_bpm = bpm
            ecg_rr = rr_ms


def ecg_leads_handler(address, *args):
    global ecg_leads_off, ecg_start
    if ecg_start is None:
        ecg_start = time.monotonic()
    ecg_leads_off = bool(args[0]) if args else True

# ─────────────────────────────────────────────
# Band power computation
# ─────────────────────────────────────────────

def compute_bands():
    global eeg_band_powers
    from scipy.signal import welch as welch_psd
    powers = {}
    for ch in CHANNELS:
        buf = eeg_buffers[ch]
        if len(buf) < SFREQ:
            continue
        data = np.array(buf[-WINDOW:])
        ch_powers = {}
        freqs, psd = welch_psd(data, fs=SFREQ, nperseg=min(len(data), SFREQ))
        for band, (lo, hi) in BANDS.items():
            idx = (freqs >= lo) & (freqs <= hi)
            ch_powers[band] = float(np.mean(psd[idx])) if np.any(idx) else 0.0
        powers[ch] = ch_powers
    eeg_band_powers = powers

# ─────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────

def bar(value, max_val, width=20):
    if max_val <= 0:
        return " " * width
    filled = int(min(value / max_val, 1.0) * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def render_trace(values, width=ECG_TRACE_WIDTH, height=5):
    if len(values) < 3:
        return "    Waiting for data..."
    vmin, vmax = min(values), max(values)
    vrange = vmax - vmin if vmax > vmin else 1.0
    lines = []
    for row in range(height):
        threshold = vmax - (row / (height - 1)) * vrange
        line = ""
        for v in values[-width:]:
            line += "\u2588" if v >= threshold else " "
        lines.append(f"    {line}")
    return "\n".join(lines)


def contact_icon(val):
    if val <= 1.5:
        return "\033[92m\u2588\033[0m"  # green
    elif val <= 2.5:
        return "\033[93m\u2593\033[0m"  # yellow
    elif val <= 3.5:
        return "\033[91m\u2592\033[0m"  # red
    else:
        return "\033[90m\u2591\033[0m"  # gray/off


def display_loop(show_eeg, show_ecg):
    last_band_calc = 0

    while True:
        time.sleep(0.3)
        now = time.monotonic()

        # Compute band powers every 0.5s
        if show_eeg and now - last_band_calc > 0.5 and eeg_start:
            compute_bands()
            last_band_calc = now

        out = "\033[2J\033[H"  # clear
        out += f"\033[96m{'=' * 70}\033[0m\n"
        out += f"  \033[1mDevice Monitor\033[0m — Cymatic Control\n"
        out += f"\033[96m{'=' * 70}\033[0m\n"

        # ─── EEG Section ─────────────────────────────
        if show_eeg:
            out += f"\n  \033[93m--- EEG (Muse 2) ---\033[0m\n"
            if eeg_start is None:
                out += f"  Waiting for /muse/eeg data...\n"
                out += f"  (Start Mind Monitor, set OSC target to this IP)\n"
            else:
                elapsed = now - eeg_start
                pps = eeg_packets / elapsed if elapsed > 1 else 0

                # Contact quality
                contacts = "  Contact: "
                for ch in CHANNELS:
                    contacts += f" {ch}:{contact_icon(eeg_contact[ch])}"
                all_good = all(eeg_contact[ch] <= 2.0 for ch in CHANNELS)
                fit_str = "  \033[92mAll good\033[0m" if all_good else "  \033[91mCheck fit\033[0m"
                contacts += f"  {fit_str}"
                out += contacts + "\n"

                out += f"  Packets: {eeg_packets}  ({pps:.0f}/s, expect ~256)\n"

                # Band powers
                if eeg_band_powers:
                    out += f"\n  Band Powers:\n"
                    band_names = list(BANDS.keys())
                    # Header
                    out += f"  {'':8s}"
                    for b in band_names:
                        out += f" {b:>7s}"
                    out += "\n"
                    # Per channel
                    for ch in CHANNELS:
                        if ch in eeg_band_powers:
                            p = eeg_band_powers[ch]
                            vals = [p.get(b, 0) for b in band_names]
                            max_v = max(vals) if vals else 1
                            out += f"  {ch:8s}"
                            for v in vals:
                                level = int(min(v / max_v, 1.0) * 5) if max_v > 0 else 0
                                blocks = "\u2588" * level + "\u2591" * (5 - level)
                                out += f"  {blocks} "
                            out += "\n"

                    # Dominant band (average across channels)
                    avg_powers = {}
                    for b in band_names:
                        vals = [eeg_band_powers[ch].get(b, 0) for ch in eeg_band_powers]
                        avg_powers[b] = np.mean(vals) if vals else 0
                    if any(v > 0 for v in avg_powers.values()):
                        dominant = max(avg_powers, key=avg_powers.get)
                        out += f"\n  Dominant: \033[96m{dominant}\033[0m"
                        # Brain state hint
                        hints = {"delta": "(deep sleep)",
                                 "theta": "(drowsy/meditative)",
                                 "alpha": "(relaxed/calm)",
                                 "beta": "(focused/alert)",
                                 "gamma": "(high processing)"}
                        out += f"  {hints.get(dominant, '')}\n"

        # ─── ECG Section ─────────────────────────────
        if show_ecg:
            out += f"\n  \033[93m--- ECG (AD8232 + ESP32) ---\033[0m\n"
            if ecg_start is None:
                out += f"  Waiting for /ecg/raw data...\n"
                out += f"  (Check ESP32 is powered and configured)\n"
            else:
                elapsed = now - ecg_start
                sps = ecg_samples / elapsed if elapsed > 1 else 0
                status = "\033[91m\u26a0 Leads off\033[0m" if ecg_leads_off else "\033[92m\u2714 Connected\033[0m"

                out += f"  Status:  {status}\n"
                out += f"  Samples: {ecg_samples}  ({sps:.0f} Hz, expect ~250)\n"

                if ecg_detector and ecg_beats > 0:
                    heart = "\u2665" if ecg_beats % 2 == 0 else "\u2661"
                    out += f"  {heart} BPM: \033[1m{ecg_bpm:.0f}\033[0m  RR: {ecg_rr:.0f}ms  Beats: {ecg_beats}\n"
                elif ecg_detector:
                    out += f"  Waiting for heartbeat...\n"

                # ASCII trace
                out += f"\n  ECG Trace:\n"
                out += render_trace(ecg_trace) + "\n"

        # ─── Footer ──────────────────────────────────
        out += f"\n  \033[2mCtrl+C to stop\033[0m\n"
        print(out, end="", flush=True)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    global ecg_detector

    parser = argparse.ArgumentParser(description="Device Monitor — test Muse 2 and/or ESP32 ECG")
    parser.add_argument("--eeg", action="store_true", help="Monitor EEG only")
    parser.add_argument("--ecg", action="store_true", help="Monitor ECG only")
    parser.add_argument("--eeg-port", type=int, default=5000, help="EEG listen port (default: 5000)")
    parser.add_argument("--ecg-port", type=int, default=5001, help="ECG listen port (default: 5001)")
    args = parser.parse_args()

    # Default: both
    show_eeg = True
    show_ecg = True
    if args.eeg and not args.ecg:
        show_ecg = False
    elif args.ecg and not args.eeg:
        show_eeg = False

    # Always try R-peak detection for ECG
    if show_ecg:
        try:
            from ecg_analysis import ECGProcessor
            ecg_detector = ECGProcessor(sample_rate=250)
        except ImportError:
            pass

    # Build dispatchers and servers
    servers = []

    if show_eeg:
        eeg_disp = dispatcher.Dispatcher()
        eeg_disp.map("/muse/eeg", eeg_handler)
        eeg_disp.map("/muse/elements/horseshoe", horseshoe_handler)
        eeg_server = osc_server.ThreadingOSCUDPServer(("0.0.0.0", args.eeg_port), eeg_disp)
        servers.append(eeg_server)

    if show_ecg:
        ecg_disp = dispatcher.Dispatcher()
        ecg_disp.map("/ecg/raw", ecg_raw_handler)
        ecg_disp.map("/ecg/leads_off", ecg_leads_handler)
        ecg_server = osc_server.ThreadingOSCUDPServer(("0.0.0.0", args.ecg_port), ecg_disp)
        servers.append(ecg_server)

    # Print startup info
    print(f"\n\033[96m{'=' * 70}\033[0m")
    print(f"  \033[1mDevice Monitor\033[0m — Cymatic Control")
    print(f"\033[96m{'=' * 70}\033[0m")
    if show_eeg:
        print(f"  EEG: listening on port {args.eeg_port} for /muse/eeg")
    if show_ecg:
        print(f"  ECG: listening on port {args.ecg_port} for /ecg/raw")
    print(f"  Waiting for data...\n")

    # Start servers
    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    # Start display once any data arrives
    def wait_and_display():
        while eeg_start is None and ecg_start is None:
            time.sleep(0.1)
        display_loop(show_eeg, show_ecg)

    threading.Thread(target=wait_and_display, daemon=True).start()

    def stop(sig, frame):
        print(f"\033[2J\033[H")
        print(f"\n  Stopped.")
        if eeg_start:
            print(f"  EEG: {eeg_packets} packets received")
        if ecg_start:
            print(f"  ECG: {ecg_samples} samples, {ecg_beats} beats detected")
        print()
        for srv in servers:
            srv.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.pause()


if __name__ == "__main__":
    main()
