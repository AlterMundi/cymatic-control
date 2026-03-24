"""
ECG Stream Test — Verify ESP32 + AD8232 is sending data.

Listens for /ecg/raw and /ecg/leads_off OSC messages from the ESP32
and displays a live terminal view: signal level, packet rate, lead-off
status, and a simple ASCII heartbeat trace.

No harmonic_shaper or muse_bridge needed — just plug in the ESP32
and run this script.

Usage:
    python test_ecg_stream.py                    # listen on port 5001
    python test_ecg_stream.py --port 5002        # different port
    python test_ecg_stream.py --detect           # also run R-peak detection
"""

import argparse
import signal
import sys
import time
import threading
from pythonosc import dispatcher, osc_server


# ─────────────────────────────────────────────
# State
# ─────────────────────────────────────────────

packets = 0
samples_total = 0
last_values = []
leads_off = False
start_time = None

# For the ASCII trace
trace_buf = []
TRACE_WIDTH = 60

# Optional R-peak detection
detector = None
beat_count = 0
last_bpm = 0.0
last_rr = 0.0


# ─────────────────────────────────────────────
# OSC Handlers
# ─────────────────────────────────────────────

def on_first_packet():
    global start_time
    if start_time is None:
        start_time = time.monotonic()


def ecg_raw_handler(address, *args):
    global packets, samples_total, last_values

    on_first_packet()

    packets += 1
    samples_total += len(args)
    last_values = list(args)

    # Feed ASCII trace (take middle sample of batch)
    if args:
        trace_buf.append(float(args[len(args) // 2]))
        if len(trace_buf) > TRACE_WIDTH:
            trace_buf.pop(0)

    # Optional R-peak detection
    if detector is not None:
        global beat_count, last_bpm, last_rr
        beats = detector.add_samples(list(args))
        for bpm, rr_ms in beats:
            beat_count += 1
            last_bpm = bpm
            last_rr = rr_ms


def leads_off_handler(address, *args):
    global leads_off
    on_first_packet()
    leads_off = bool(args[0]) if args else True


# ─────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────

def render_trace(values, width=TRACE_WIDTH, height=6):
    """Render an ASCII trace of recent ECG values."""
    if len(values) < 3:
        return "  Waiting for data..."

    vmin = min(values)
    vmax = max(values)
    vrange = vmax - vmin if vmax > vmin else 1.0

    lines = []
    for row in range(height):
        threshold = vmax - (row / (height - 1)) * vrange
        line = ""
        for v in values[-width:]:
            if abs(v - threshold) < vrange / (height * 2):
                line += "\u2588"
            elif v >= threshold:
                line += "\u2588"
            else:
                line += " "
        # Y-axis label
        if row == 0:
            label = f"{vmax:.0f}"
        elif row == height - 1:
            label = f"{vmin:.0f}"
        else:
            label = ""
        lines.append(f"  {label:>5s} \u2502{line}\u2502")

    return "\n".join(lines)


def display_loop():
    """Periodic display update."""
    while True:
        time.sleep(0.25)

        elapsed = time.monotonic() - start_time if start_time else 0
        pps = packets / elapsed if elapsed > 1 else 0
        sps = samples_total / elapsed if elapsed > 1 else 0

        # Clear and redraw
        status_icon = "\033[91m\u26a0 LEADS OFF\033[0m" if leads_off else "\033[92m\u2714 Connected\033[0m"

        # Header
        out = f"\033[2J\033[H"  # clear screen
        out += f"\033[96m{'='*70}\033[0m\n"
        out += f"  \033[1mECG Stream Test\033[0m — AD8232 + ESP32\n"
        out += f"\033[96m{'='*70}\033[0m\n\n"

        # Stats
        out += f"  Status:    {status_icon}\n"
        out += f"  Packets:   {packets}  ({pps:.1f}/s)\n"
        out += f"  Samples:   {samples_total}  ({sps:.0f} Hz)\n"
        out += f"  Elapsed:   {elapsed:.0f}s\n"

        if last_values:
            vals_str = " ".join(f"{v:.0f}" for v in last_values[:8])
            out += f"  Last batch: [{vals_str}]\n"
            avg = sum(last_values) / len(last_values)
            out += f"  ADC mean:  {avg:.0f}  (expect ~2048 at rest)\n"

        # R-peak detection stats (if enabled)
        if detector is not None:
            out += f"\n  \033[93m--- R-Peak Detection ---\033[0m\n"
            if beat_count > 0:
                beat_icon = "\u2665" if beat_count % 2 == 0 else "\u2661"
                out += f"  {beat_icon} Beats: {beat_count}  BPM: {last_bpm:.1f}  RR: {last_rr:.0f}ms\n"
            else:
                out += f"  Waiting for first heartbeat...\n"

        # ASCII trace
        out += f"\n  \033[93m--- ECG Trace ---\033[0m\n"
        out += render_trace(trace_buf) + "\n"

        out += f"\n  \033[2mCtrl+C to stop\033[0m\n"

        print(out, end="", flush=True)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    global detector

    parser = argparse.ArgumentParser(
        description="ECG Stream Test — verify ESP32 + AD8232 data"
    )
    parser.add_argument("--port", type=int, default=5001,
                        help="Port to listen on (default: 5001)")
    parser.add_argument("--detect", action="store_true",
                        help="Enable R-peak detection (shows BPM)")
    args = parser.parse_args()

    if args.detect:
        try:
            from ecg_analysis import ECGProcessor
            detector = ECGProcessor(sample_rate=250)
            print("  R-peak detection enabled.")
        except ImportError:
            print("  WARNING: ecg_analysis.py not found, --detect disabled.")

    disp = dispatcher.Dispatcher()
    disp.map("/ecg/raw", ecg_raw_handler)
    disp.map("/ecg/leads_off", leads_off_handler)

    server = osc_server.ThreadingOSCUDPServer(("0.0.0.0", args.port), disp)

    print(f"\n\033[96m{'='*70}\033[0m")
    print(f"  \033[1mECG Stream Test\033[0m — AD8232 + ESP32")
    print(f"\033[96m{'='*70}\033[0m")
    print(f"  Listening on port {args.port} for /ecg/raw ...")
    print(f"  Make sure the ESP32 is configured to send to this IP:port.")
    print(f"  Waiting for first packet...\n")

    # Start display thread once we get data
    display_thread = threading.Thread(target=display_loop, daemon=True)

    def check_start():
        """Start display once first packet arrives."""
        while start_time is None:
            time.sleep(0.1)
        display_thread.start()

    threading.Thread(target=check_start, daemon=True).start()

    def stop(sig, frame):
        print(f"\033[2J\033[H")
        print(f"\n  Stopped. Received {packets} packets ({samples_total} samples).")
        if detector and beat_count > 0:
            print(f"  Detected {beat_count} heartbeats. Last BPM: {last_bpm:.1f}")
        print()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    server.serve_forever()


if __name__ == "__main__":
    main()
