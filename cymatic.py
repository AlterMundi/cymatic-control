#!/usr/bin/env python3
"""
Cymatic Control — Interactive Session Launcher

Guides you through configuring and launching cymatic control sessions.
No need to remember script names, flags, or port numbers.

    python cymatic.py
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent


# ─────────────────────────────────────────────
# ANSI Colors (auto-disabled when not a TTY)
# ─────────────────────────────────────────────

class C:
    _on = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    DIM = "\033[2m" if _on else ""

    RED = "\033[31m" if _on else ""
    GREEN = "\033[32m" if _on else ""
    YELLOW = "\033[33m" if _on else ""
    BLUE = "\033[34m" if _on else ""
    CYAN = "\033[36m" if _on else ""

    BRED = "\033[91m" if _on else ""
    BGREEN = "\033[92m" if _on else ""
    BYELLOW = "\033[93m" if _on else ""
    BBLUE = "\033[94m" if _on else ""
    BCYAN = "\033[96m" if _on else ""


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

def load_config():
    path = ROOT / "config.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


CFG = load_config()


# ─────────────────────────────────────────────
# UI Helpers
# ─────────────────────────────────────────────

def clear():
    os.system("clear" if os.name != "nt" else "cls")


def banner():
    print(f"""
{C.BCYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {C.BOLD}C Y M A T I C   C O N T R O L{C.RESET}{C.BCYAN}                             ║
║   {C.DIM}Interactive Session Launcher{C.RESET}{C.BCYAN}                               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")


def header(title):
    w = max(len(title) + 4, 44)
    print(f"\n{C.CYAN}{'─' * w}{C.RESET}")
    print(f"  {C.BOLD}{title}{C.RESET}")
    print(f"{C.CYAN}{'─' * w}{C.RESET}\n")


def menu(title, options, *, back=True, quit_opt=False):
    """Display a numbered menu and return the chosen key, or None for back."""
    header(title)
    keys = []
    for key, label in options:
        if key == "---":
            print(f"  {C.DIM}{'─' * 42}{C.RESET}")
            continue
        keys.append(key)
        tag = C.BYELLOW if key.isdigit() else C.DIM
        print(f"  {tag}{key}{C.RESET}  {label}")

    if back:
        print(f"\n  {C.DIM}b  Back{C.RESET}")
    if quit_opt:
        print(f"  {C.DIM}q  Quit{C.RESET}")
    print()

    while True:
        try:
            choice = input(f"  {C.BGREEN}▸{C.RESET} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if choice == "b" and back:
            return None
        if choice == "q" and quit_opt:
            return "q"
        if choice in keys:
            return choice
        print(f"  {C.RED}Invalid choice.{C.RESET}")


def ask(prompt, default=None):
    """Ask for a string with an optional default."""
    if default is not None:
        display = f"  {prompt} {C.DIM}[{default}]{C.RESET}: "
    else:
        display = f"  {prompt}: "
    try:
        answer = input(display).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default if default is not None else ""
    return answer if answer else (default if default is not None else "")


def ask_float(prompt, default):
    while True:
        raw = ask(prompt, str(default))
        try:
            return float(raw)
        except ValueError:
            print(f"  {C.RED}Enter a number.{C.RESET}")


def ask_int(prompt, default):
    while True:
        raw = ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"  {C.RED}Enter an integer.{C.RESET}")


def ask_yn(prompt, default=True):
    tag = "Y/n" if default else "y/N"
    try:
        raw = input(f"  {prompt} {C.DIM}[{tag}]{C.RESET}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not raw:
        return default
    return raw in ("y", "yes")


def pick(prompt, choices, default=None):
    joined = "/".join(choices)
    while True:
        answer = ask(f"{prompt} ({joined})", default)
        if answer in choices:
            return answer
        print(f"  {C.RED}Must be one of: {joined}{C.RESET}")


def pause():
    try:
        input(f"\n  {C.DIM}Press Enter to continue...{C.RESET}")
    except (EOFError, KeyboardInterrupt):
        pass


# ─────────────────────────────────────────────
# Process Manager
# ─────────────────────────────────────────────

class ProcessManager:
    def __init__(self):
        self.procs = []

    def launch(self, name, cmd, *, background=False):
        label = f"{C.DIM}(background){C.RESET}" if background else f"{C.GREEN}(main){C.RESET}"
        pretty = " ".join(cmd).replace(sys.executable, "python")
        print(f"  {C.GREEN}▶{C.RESET} {name} {label}")
        print(f"    {C.DIM}$ {pretty}{C.RESET}")
        proc = subprocess.Popen(cmd, cwd=str(ROOT))
        self.procs.append((name, proc))
        if background:
            time.sleep(0.6)
        return proc

    def wait(self):
        if not self.procs:
            return
        print(f"\n  {C.BCYAN}Session running — Ctrl+C to stop all.{C.RESET}\n")
        try:
            while True:
                all_done = True
                for name, proc in self.procs:
                    if proc.poll() is None:
                        all_done = False
                if all_done:
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        self.stop_all()

    def stop_all(self):
        print(f"\n\n  {C.YELLOW}Stopping session...{C.RESET}")
        for name, proc in reversed(self.procs):
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        for name, proc in self.procs:
            try:
                proc.wait(timeout=5)
                print(f"    {C.DIM}✓ {name} stopped{C.RESET}")
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"    {C.RED}✗ {name} killed{C.RESET}")
        self.procs.clear()
        print()


# ─────────────────────────────────────────────
# Command Builders
# ─────────────────────────────────────────────

PY = sys.executable


def cmd_simulate_eeg(ip="127.0.0.1", port=5000, speed=1.0, transition=3.0):
    return [PY, "simulate_eeg.py",
            "--ip", ip, "--port", str(port),
            "--speed", str(speed), "--transition", str(transition)]


def cmd_simulate_tilt(ip="127.0.0.1", port=5000, speed=1.0, depth=0.20):
    return [PY, "simulate_tilt.py",
            "--ip", ip, "--port", str(port),
            "--speed", str(speed), "--depth", str(depth)]


def cmd_hr_relay(mode, ip="127.0.0.1", port=5000, **kw):
    c = [PY, "hr_relay.py", "--mode", mode,
         "--target-ip", ip, "--target-port", str(port)]
    if mode == "simulate":
        c += ["--bpm", str(kw.get("bpm", 72)),
              "--variation", str(kw.get("variation", 3.0))]
    elif mode == "ble":
        if kw.get("device"):
            c += ["--device", kw["device"]]
        c += ["--scan-timeout", str(kw.get("scan_timeout", 10.0))]
    elif mode == "fitbit-api":
        if kw.get("client_id"):
            c += ["--client-id", kw["client_id"]]
        if kw.get("client_secret"):
            c += ["--client-secret", kw["client_secret"]]
        c += ["--poll-interval", str(kw.get("poll_interval", 15.0))]
    return c


def cmd_midi_relay(ip="127.0.0.1", port=5000, **kw):
    c = [PY, "midi_relay.py",
         "--target-ip", ip, "--target-port", str(port)]
    if kw.get("midi_port"):
        c += ["--port", kw["midi_port"]]
    if kw.get("cc"):
        c += ["--cc", str(kw["cc"])]
    return c


def cmd_muse_bridge(param, **kw):
    mb = CFG.get("muse_bridge", {})
    c = [PY, "muse_bridge.py", "--param", param,
         "--shaper-ip", str(kw.get("shaper_ip", mb.get("shaper_ip", "127.0.0.1"))),
         "--shaper-port", str(kw.get("shaper_port", mb.get("shaper_port", 9002))),
         "--shaper-api", str(kw.get("shaper_api", mb.get("shaper_api", "http://127.0.0.1:8080"))),
         "--listen-port", str(kw.get("listen_port", 5000))]
    if kw.get("depth") is not None:
        c += ["--depth", str(kw["depth"])]
    if kw.get("gain_depth") is not None:
        c += ["--gain-depth", str(kw["gain_depth"])]
    for flag, arg in [("update_rate", "--update-rate"), ("osc_rate", "--osc-rate"),
                      ("window", "--window"), ("smoothing", "--smoothing")]:
        if kw.get(flag) is not None:
            c += [arg, str(kw[flag])]
    if kw.get("pulse") is not None:
        c += ["--pulse", str(kw["pulse"])]
    return c


def cmd_osc_bridge(actuator_ip, **kw):
    return [PY, "osc_bridge.py",
            "--actuator-ip", actuator_ip,
            "--actuator-port", str(kw.get("actuator_port", 53280)),
            "--listen-port", str(kw.get("listen_port", 5000)),
            "--mode", kw.get("mode", "spectral"),
            "--update-rate", str(kw.get("update_rate", 2.0)),
            "--harmonic-multiplier", str(kw.get("harmonic_multiplier", 32)),
            "--window", str(kw.get("window", 1.0))]


def cmd_eeg_harmonic_bridge(**kw):
    c = [PY, "eeg_harmonic_bridge.py",
         "--listen-port", str(kw.get("listen_port", 5000)),
         "--f1", str(kw.get("f1", 64.0)),
         "--update-rate", str(kw.get("update_rate", 2.0)),
         "--window", str(kw.get("window", 1.0))]
    if kw.get("surge_ip"):
        c += ["--surge-ip", kw["surge_ip"],
              "--surge-port", str(kw.get("surge_port", 53280))]
    if kw.get("actuator_ip"):
        c += ["--actuator-ip", kw["actuator_ip"],
              "--actuator-port", str(kw.get("actuator_port", 53280))]
    if kw.get("stereo"):
        c += ["--stereo"]
    if kw.get("mono"):
        c += ["--mono"]
    return c


# ─────────────────────────────────────────────
# Preview + Launch
# ─────────────────────────────────────────────

def preview_and_launch(steps):
    """Show commands and confirm before launching.

    *steps* is a list of (name, cmd, background_bool) tuples.
    """
    header("Session Preview")

    for i, (name, cmd, bg) in enumerate(steps, 1):
        kind = f"{C.DIM}background{C.RESET}" if bg else f"{C.GREEN}main{C.RESET}"
        pretty = " ".join(cmd).replace(PY, "python")
        print(f"  {C.BYELLOW}{i}.{C.RESET} {name} ({kind})")
        print(f"     {C.DIM}$ {pretty}{C.RESET}")
        print()

    if not ask_yn("Launch session?"):
        return

    do_launch(steps)


def do_launch(steps):
    header("Launching")
    pm = ProcessManager()

    for name, cmd, bg in steps:
        if bg:
            pm.launch(name, cmd, background=True)

    for name, cmd, bg in steps:
        if not bg:
            pm.launch(name, cmd, background=False)

    pm.wait()


# ─────────────────────────────────────────────
# Quick-start Presets
# ─────────────────────────────────────────────

def preset_test():
    header("Quick Start — Test Without Hardware")
    print(f"  Launches three processes with simulated inputs:")
    print(f"    1. {C.BOLD}EEG Simulator{C.RESET}  — cycles through 7 brain states")
    print(f"    2. {C.BOLD}HR Relay{C.RESET}       — synthetic heartbeat at 72 BPM")
    print(f"    3. {C.BOLD}Muse Bridge{C.RESET}    — both mode (phase + gain)")
    print()
    print(f"  {C.DIM}No hardware required. Great for tuning & demos.{C.RESET}")
    print()

    if not ask_yn("Launch?"):
        return

    do_launch([
        ("EEG Simulator", cmd_simulate_eeg(), True),
        ("HR Relay", cmd_hr_relay("simulate", bpm=72), True),
        ("Muse Bridge", cmd_muse_bridge("both", depth=30, pulse=0.15), False),
    ])


def preset_muse_phase():
    header("Quick Start — Muse Phase Control")
    print(f"  {C.BOLD}Muse 2{C.RESET} → phase rotation of harmonic shaper voices.")
    print(f"  Each sensor drives its matched harmonic's rotation speed.")
    print()
    print(f"  {C.YELLOW}Requires:{C.RESET} Muse 2 streaming via Mind Monitor to port 5000")
    print()

    depth = ask_float("Phase depth (max °/s)", 30.0)

    if not ask_yn("Launch?"):
        return

    do_launch([
        ("Muse Bridge", cmd_muse_bridge("phase", depth=depth), False),
    ])


def preset_full():
    header("Quick Start — Full Session")
    print(f"  All inputs active: Muse 2 + Launchpad + BLE heart rate.")
    print(f"    1. {C.BOLD}MIDI Relay{C.RESET}   — Launchpad slider → gain depth")
    print(f"    2. {C.BOLD}HR Relay{C.RESET}     — BLE heart rate sensor → pulse")
    print(f"    3. {C.BOLD}Muse Bridge{C.RESET}  — both mode (phase from EEG, gain from slider)")
    print()
    print(f"  {C.YELLOW}Requires:{C.RESET}")
    print(f"    • Muse 2 streaming via Mind Monitor (port 5000)")
    print(f"    • MIDI controller (Launchpad)")
    print(f"    • BLE HR sensor (Fitbit Charge 6 etc.)")
    print()

    if not ask_yn("Launch?"):
        return

    do_launch([
        ("MIDI Relay", cmd_midi_relay(), True),
        ("HR Relay", cmd_hr_relay("ble"), True),
        ("Muse Bridge", cmd_muse_bridge("both", depth=30, pulse=0.15), False),
    ])


# ─────────────────────────────────────────────
# Wizard: Harmonic Shaper Session
# ─────────────────────────────────────────────

def ask_eeg_source(listen_port):
    """Pick EEG source. Returns list of background steps (may be empty)."""
    choice = menu("EEG Input", [
        ("1", f"Muse 2 live {C.DIM}(via Mind Monitor OSC){C.RESET}"),
        ("2", f"EEG Simulator {C.DIM}(7 brain states, no hardware){C.RESET}"),
        ("3", f"Tilt Simulator {C.DIM}(alpha/beta stages for gain tilt observation){C.RESET}"),
    ])
    if choice is None:
        return None
    if choice == "1":
        return []
    if choice == "2":
        speed = ask_float("Simulation speed multiplier", 1.0)
        return [("EEG Simulator", cmd_simulate_eeg(port=listen_port, speed=speed), True)]
    if choice == "3":
        speed = ask_float("Simulation speed multiplier", 1.0)
        depth = ask_float("Tilt preview depth (0-1)", 0.20)
        return [("Tilt Simulator", cmd_simulate_tilt(port=listen_port, speed=speed, depth=depth), True)]


def ask_hr_source(listen_port):
    """Pick heart rate source. Returns (hr_steps, pulse_amplitude)."""
    choice = menu("Heart Rate Input", [
        ("1", f"None {C.DIM}(no heartbeat pulse){C.RESET}"),
        ("2", f"Simulate {C.DIM}(synthetic beats at configurable BPM){C.RESET}"),
        ("3", f"BLE {C.DIM}(Fitbit Charge 6 / any BLE HR sensor){C.RESET}"),
        ("4", f"Fitbit Web API {C.DIM}(cloud, requires OAuth){C.RESET}"),
    ])
    if choice is None:
        return None, 0.0
    if choice == "1":
        return [], 0.0

    pulse = ask_float("Pulse amplitude (0-1, how much gain boost per beat)", 0.15)

    if choice == "2":
        bpm = ask_float("Base BPM", 72.0)
        var = ask_float("BPM variation +/-", 3.0)
        step = ("HR Relay (sim)", cmd_hr_relay("simulate", port=listen_port, bpm=bpm, variation=var), True)
        return [step], pulse

    if choice == "3":
        dev = ask("BLE device name filter (Enter = any)", "")
        kw = {"device": dev} if dev else {}
        step = ("HR Relay (BLE)", cmd_hr_relay("ble", port=listen_port, **kw), True)
        return [step], pulse

    if choice == "4":
        cid = ask("Fitbit OAuth client ID", None)
        csec = ask("Fitbit OAuth client secret", None)
        step = ("HR Relay (Fitbit)", cmd_hr_relay("fitbit-api", port=listen_port,
                                                   client_id=cid, client_secret=csec), True)
        return [step], pulse


def wizard_shaper():
    choice = menu("Harmonic Shaper — Choose Session", [
        ("1", f"Build step-by-step {C.DIM}(pick your inputs → system picks the mode){C.RESET}"),
        ("---", ""),
        ("2", f"{C.BGREEN}Quick: Test without hardware{C.RESET}"),
        ("3", f"{C.BGREEN}Quick: Muse-only phase{C.RESET}"),
        ("4", f"{C.BGREEN}Quick: Full session{C.RESET} {C.DIM}(Muse + Launchpad + BLE HR){C.RESET}"),
    ])
    if choice is None:
        return
    if choice == "2":
        return preset_test()
    if choice == "3":
        return preset_muse_phase()
    if choice == "4":
        return preset_full()

    _shaper_step_by_step()


def _shaper_step_by_step():
    """Signal-chain wizard: pick inputs, system infers the mode."""
    mb = CFG.get("muse_bridge", {})
    listen_port = 5000
    all_steps = []

    n_steps = 3

    # ─── Step 1: EEG → Phase rotation ──────────────────────────────

    print(f"  {C.DIM}Each sensor's brainwave band drives its matched harmonic's")
    print(f"  rotation speed — the cymatic pattern evolves with your brain.{C.RESET}\n")

    eeg = menu(f"Step 1/{n_steps} — EEG → Phase Rotation", [
        ("1", f"Muse 2 {C.DIM}(live via Mind Monitor OSC){C.RESET}"),
        ("2", f"EEG Simulator {C.DIM}(cycles through 7 brain states){C.RESET}"),
        ("3", f"Tilt Simulator {C.DIM}(alpha/beta stages for gain observation){C.RESET}"),
        ("---", ""),
        ("4", f"Skip {C.DIM}(no EEG — heartbeat pulse only){C.RESET}"),
    ])
    if eeg is None:
        return

    has_eeg = eeg != "4"
    eeg_labels = {"1": "Muse 2 (live)", "2": "EEG Simulator", "3": "Tilt Simulator"}

    if eeg == "2":
        speed = ask_float("Simulation speed", 1.0)
        all_steps.append(("EEG Simulator",
                          cmd_simulate_eeg(port=listen_port, speed=speed), True))
    elif eeg == "3":
        speed = ask_float("Simulation speed", 1.0)
        all_steps.append(("Tilt Simulator",
                          cmd_simulate_tilt(port=listen_port, speed=speed), True))

    # ─── Step 2: Heart rate → Gain pulse ───────────────────────────

    print(f"  {C.DIM}Each heartbeat creates a visible \"breathing\" in the cymatic")
    print(f"  pattern — a short gain swell that syncs to your pulse.{C.RESET}\n")

    hr = menu(f"Step 2/{n_steps} — Heart Rate → Gain Pulse", [
        ("1", f"Skip {C.DIM}(no heartbeat pulse){C.RESET}"),
        ("2", f"Simulate {C.DIM}(synthetic beats at configurable BPM){C.RESET}"),
        ("3", f"BLE sensor {C.DIM}(Fitbit Charge 6 / any BLE HR device){C.RESET}"),
        ("4", f"Fitbit Web API {C.DIM}(cloud polling, OAuth required){C.RESET}"),
    ])
    if hr is None:
        return

    has_hr = hr != "1"
    hr_labels = {"2": "Simulated", "3": "BLE sensor", "4": "Fitbit Web API"}
    pulse = 0.0

    if has_hr:
        pulse = ask_float("Pulse amplitude (0-1, gain boost per heartbeat)", 0.15)
        if hr == "2":
            bpm = ask_float("Base BPM", 72.0)
            var = ask_float("BPM variation +/-", 3.0)
            all_steps.append(("HR Relay (sim)",
                              cmd_hr_relay("simulate", port=listen_port,
                                           bpm=bpm, variation=var), True))
        elif hr == "3":
            dev = ask("BLE device name filter (Enter = any)", "")
            kw = {"device": dev} if dev else {}
            all_steps.append(("HR Relay (BLE)",
                              cmd_hr_relay("ble", port=listen_port, **kw), True))
        elif hr == "4":
            cid = ask("Fitbit OAuth client ID", "")
            csec = ask("Fitbit OAuth client secret", "")
            all_steps.append(("HR Relay (Fitbit)",
                              cmd_hr_relay("fitbit-api", port=listen_port,
                                           client_id=cid, client_secret=csec), True))

    # ─── Step 3: MIDI → Gain tilt depth ────────────────────────────

    has_midi = False
    fixed_gain_depth = None

    if has_eeg:
        print(f"  {C.DIM}EEG alpha/beta ratio tilts the harmonic gain curve:")
        print(f"  relaxed → warm (lower harmonics), focused → bright (upper).")
        print(f"  A physical slider controls how much EEG affects the gains.{C.RESET}\n")

        gain = menu(f"Step 3/{n_steps} — MIDI → Gain Tilt Depth", [
            ("1", f"Skip {C.DIM}(no gain modulation — phase and/or pulse only){C.RESET}"),
            ("2", f"MIDI controller {C.DIM}(Launchpad slider controls depth live){C.RESET}"),
            ("3", f"Fixed depth {C.DIM}(constant EEG gain modulation, no slider){C.RESET}"),
        ])
        if gain is None:
            return
        if gain == "2":
            has_midi = True
            midi_port = ask("MIDI port name filter (Enter = auto-detect)", "")
            kw = {"midi_port": midi_port} if midi_port else {}
            all_steps.append(("MIDI Relay",
                              cmd_midi_relay(port=listen_port, **kw), True))
        elif gain == "3":
            fixed_gain_depth = ask_float("Gain depth (0-1, how much EEG tilts gains)", 0.20)
    else:
        print(f"\n  {C.DIM}Skipping step 3 — gain tilt needs EEG input.{C.RESET}")

    # ─── Validation ────────────────────────────────────────────────

    if not has_eeg and not has_hr:
        print(f"\n  {C.RED}Nothing to run — pick at least EEG or heart rate.{C.RESET}")
        pause()
        return

    # ─── Infer mode ────────────────────────────────────────────────

    if has_eeg and (has_midi or fixed_gain_depth is not None):
        param = "both"
    elif has_eeg:
        param = "phase"
    else:
        param = "phase"  # heartbeat-only: depth 0

    # ─── Build bridge kwargs ───────────────────────────────────────

    bridge_kw = {
        "listen_port": listen_port,
        "shaper_ip": mb.get("shaper_ip", "127.0.0.1"),
        "shaper_port": mb.get("shaper_port", 9002),
        "shaper_api": mb.get("shaper_api", "http://127.0.0.1:8080"),
        "update_rate": mb.get("update_rate_hz", 4.0),
        "osc_rate": mb.get("osc_rate_hz", 30.0),
        "window": mb.get("window_seconds", 1.0),
        "smoothing": mb.get("smoothing_alpha", 0.25),
        "pulse": pulse,
    }

    if param == "phase":
        bridge_kw["depth"] = 30.0 if has_eeg else 0.0
    elif param == "both":
        bridge_kw["depth"] = 30.0
        if has_midi:
            bridge_kw["gain_depth"] = 0.0
        elif fixed_gain_depth is not None:
            bridge_kw["gain_depth"] = fixed_gain_depth

    # ─── Summary ───────────────────────────────────────────────────

    mode_labels = {"phase": "PHASE ROTATION", "gain": "GAIN TILT", "both": "PHASE + GAIN"}
    header("Session Summary")

    if has_eeg:
        print(f"  {C.BCYAN}EEG{C.RESET}   → {C.BOLD}Phase rotation{C.RESET}  "
              f"source: {eeg_labels[eeg]}")
    else:
        print(f"  {C.DIM}EEG   → (skipped){C.RESET}")

    if has_hr:
        print(f"  {C.BCYAN}HR{C.RESET}    → {C.BOLD}Gain pulse{C.RESET}      "
              f"source: {hr_labels[hr]}  amplitude: {int(pulse * 100)}%")
    else:
        print(f"  {C.DIM}HR    → (skipped){C.RESET}")

    if has_midi:
        print(f"  {C.BCYAN}MIDI{C.RESET}  → {C.BOLD}Gain tilt{C.RESET}       "
              f"slider controls depth (0–100%)")
    elif fixed_gain_depth is not None:
        print(f"  {C.BCYAN}Gain{C.RESET}  → {C.BOLD}Gain tilt{C.RESET}       "
              f"fixed depth: {int(fixed_gain_depth * 100)}%")
    else:
        print(f"  {C.DIM}MIDI  → (skipped){C.RESET}")

    print(f"\n  {C.BYELLOW}Resolved mode: {mode_labels[param]}{C.RESET}")
    print()

    # ─── Customize? ────────────────────────────────────────────────

    if ask_yn("Customize advanced parameters?", False):
        bridge_kw = _customize_bridge(param, bridge_kw)

    all_steps.append(("Muse Bridge", cmd_muse_bridge(param, **bridge_kw), False))
    preview_and_launch(all_steps)


def _customize_bridge(param, kw):
    header("Advanced Parameters")

    kw["shaper_ip"] = ask("Harmonic Shaper IP", kw["shaper_ip"])
    kw["shaper_port"] = ask_int("Shaper OSC port", kw["shaper_port"])
    kw["shaper_api"] = ask("Shaper HTTP API URL", kw["shaper_api"])
    kw["listen_port"] = ask_int("Listen port (Muse OSC + /bridge/*)", kw["listen_port"])

    if param in ("phase", "both"):
        kw["depth"] = ask_float("Phase depth — max °/s rotation", kw["depth"])
        kw["osc_rate"] = ask_float("Phase output rate (Hz, for smooth interpolation)", kw["osc_rate"])
    if param == "gain":
        kw["depth"] = ask_float("Gain depth (0-1 fraction of base)", kw["depth"])
    if param == "both":
        kw["gain_depth"] = ask_float("Initial gain depth (0 = slider only)", kw.get("gain_depth", 0.0))

    kw["update_rate"] = ask_float("EEG analysis rate (Hz)", kw["update_rate"])
    kw["window"] = ask_float("Analysis window (seconds)", kw["window"])
    kw["smoothing"] = ask_float("EMA smoothing alpha (0-1)", kw["smoothing"])
    kw["pulse"] = ask_float("Heartbeat pulse amplitude (0 = off)", kw["pulse"])

    return kw


# ─────────────────────────────────────────────
# Wizard: Direct Actuator Bridge
# ─────────────────────────────────────────────

def wizard_actuator():
    header("Direct Actuator Bridge — EEG → ESP32")
    print(f"  Maps Muse 2 EEG directly to ESP32 actuator via OSC /fnote.")
    print(f"  No harmonic_shaper in the loop — EEG drives vibration directly.")
    print()

    pb = CFG.get("playback", {})
    actuator_ip = ask("ESP32 Beacon IP", pb.get("actuator_ip", ""))
    if not actuator_ip:
        print(f"  {C.RED}ESP32 IP is required.{C.RESET}")
        return

    mode = pick("Mapping mode", ["spectral", "band_power", "concentration"], "spectral")
    listen_port = ask_int("Listen port", 5000)

    eeg_steps = ask_eeg_source(listen_port)
    if eeg_steps is None:
        return

    kw = {
        "actuator_port": ask_int("ESP32 OSC port", pb.get("actuator_port", 53280)),
        "listen_port": listen_port,
        "mode": mode,
        "update_rate": ask_float("Update rate (Hz)", 2.0),
        "harmonic_multiplier": ask_int("Harmonic multiplier (EEG freq × N)", pb.get("harmonic_multiplier", 32)),
        "window": ask_float("Analysis window (s)", 1.0),
    }

    steps = list(eeg_steps)
    steps.append(("OSC Bridge", cmd_osc_bridge(actuator_ip, **kw), False))

    preview_and_launch(steps)


# ─────────────────────────────────────────────
# Wizard: Harmonic Series Bridge
# ─────────────────────────────────────────────

def wizard_harmonic():
    header("Harmonic Series Bridge — EEG → Surge XT + ESP32")
    print(f"  Each Muse 2 sensor drives a harmonic voice in the natural series.")
    print(f"  Includes filter modulation, coherence-based fundamental, and")
    print(f"  optional stereo asymmetry mapping.")
    print()

    surge_ip = ask("Surge XT IP (Enter to skip)", "")
    surge_port = 53280
    if surge_ip:
        surge_port = ask_int("Surge XT OSC port", 53280)

    pb = CFG.get("playback", {})
    actuator_ip = ask("ESP32 Beacon IP (Enter to skip)", pb.get("actuator_ip", ""))
    actuator_port = 53280
    if actuator_ip:
        actuator_port = ask_int("ESP32 port", 53280)

    if not surge_ip and not actuator_ip:
        print(f"  {C.RED}At least one target is required (Surge XT or ESP32).{C.RESET}")
        return

    stereo = ask_yn("Enable stereo? (L/R brain asymmetry scales harmonic gain)", False)
    f1 = ask_float("Fundamental frequency (Hz)", 64.0)
    listen_port = ask_int("Listen port", 5000)
    update_rate = ask_float("Update rate (Hz)", 2.0)

    eeg_steps = ask_eeg_source(listen_port)
    if eeg_steps is None:
        return

    kw = {
        "listen_port": listen_port,
        "f1": f1,
        "update_rate": update_rate,
        "window": 1.0,
        "stereo": stereo,
        "mono": not stereo,
    }
    if surge_ip:
        kw["surge_ip"] = surge_ip
        kw["surge_port"] = surge_port
    if actuator_ip:
        kw["actuator_ip"] = actuator_ip
        kw["actuator_port"] = actuator_port

    steps = list(eeg_steps)
    steps.append(("Harmonic Bridge", cmd_eeg_harmonic_bridge(**kw), False))

    preview_and_launch(steps)


# ─────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────

def wizard_utilities():
    choice = menu("Utilities", [
        ("1", f"EEG Simulator {C.DIM}(standalone mock brain data){C.RESET}"),
        ("2", f"Tilt Simulator {C.DIM}(alpha/beta stages){C.RESET}"),
        ("3", f"HR Relay {C.DIM}(standalone heart rate source){C.RESET}"),
        ("---", ""),
        ("4", f"List MIDI ports"),
        ("5", f"Run tests"),
    ])
    if choice is None:
        return

    if choice == "1":
        ip = ask("Target IP", "127.0.0.1")
        port = ask_int("Target port", 5000)
        speed = ask_float("Speed multiplier", 1.0)
        preview_and_launch([
            ("EEG Simulator", cmd_simulate_eeg(ip, port, speed), False),
        ])

    elif choice == "2":
        ip = ask("Target IP", "127.0.0.1")
        port = ask_int("Target port", 5000)
        speed = ask_float("Speed multiplier", 1.0)
        depth = ask_float("Preview depth", 0.20)
        preview_and_launch([
            ("Tilt Simulator", cmd_simulate_tilt(ip, port, speed, depth), False),
        ])

    elif choice == "3":
        mode = pick("HR mode", ["simulate", "ble", "fitbit-api"], "simulate")
        port = ask_int("Target port", 5000)
        kw = {}
        if mode == "simulate":
            kw["bpm"] = ask_float("BPM", 72.0)
            kw["variation"] = ask_float("Variation +/-", 3.0)
        elif mode == "ble":
            dev = ask("BLE device name filter (Enter = any)", "")
            if dev:
                kw["device"] = dev
        elif mode == "fitbit-api":
            kw["client_id"] = ask("Fitbit client ID", "")
            kw["client_secret"] = ask("Fitbit client secret", "")
        preview_and_launch([
            ("HR Relay", cmd_hr_relay(mode, port=port, **kw), False),
        ])

    elif choice == "4":
        print()
        subprocess.run([PY, "midi_relay.py", "--list"], cwd=str(ROOT))
        pause()

    elif choice == "5":
        print()
        subprocess.run([PY, "-m", "pytest", "tests/", "-v"], cwd=str(ROOT))
        pause()


# ─────────────────────────────────────────────
# Architecture Overview
# ─────────────────────────────────────────────

def show_architecture():
    header("System Architecture")
    print(f"""
  {C.DIM}┌──────────────┐    ┌──────────────────┐    ┌────────────────┐
  │ {C.RESET}{C.BOLD}Muse 2{C.RESET}{C.DIM}       │    │ {C.RESET}{C.BOLD}harmonic_shaper{C.RESET}{C.DIM}  │    │ {C.RESET}{C.BOLD}ESP32 Beacon{C.RESET}{C.DIM}   │
  │ (Mind Monitor)│    │ (OSC :9002)      │    │ (OSC :53280)   │
  └──────┬───────┘    └────────▲─────────┘    └───────▲────────┘
         │ /muse/eeg           │ /shaper/harmonic/    │ /fnote
         ▼                     │ N/gain  N/phase      │
  {C.RESET}{C.CYAN}┌──────────────────────────┴──────────────────────────┴──────┐
  │                      muse_bridge.py                       │
  │              (phase rotation + gain tilt)                  │
  └──────────▲──────────────────────▲───────────────────────── ┘{C.RESET}{C.DIM}
             │ /bridge/heartbeat    │ /bridge/gain_depth
             │                      │
      ┌──────┴──────┐       ┌──────┴──────┐
      │ {C.RESET}{C.BOLD}hr_relay.py{C.RESET}{C.DIM}  │       │{C.RESET}{C.BOLD}midi_relay.py{C.RESET}{C.DIM}│
      │ sim/BLE/API │       │ Launchpad   │
      └─────────────┘       └─────────────┘{C.RESET}

  {C.DIM}Standalone bridges (no harmonic_shaper):
    osc_bridge.py          — Muse 2 EEG → ESP32 directly
    eeg_harmonic_bridge.py — Muse 2 EEG → Surge XT + ESP32{C.RESET}
""")
    pause()


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    while True:
        clear()
        banner()

        choice = menu("Main Menu", [
            ("1", f"{C.BOLD}Harmonic Shaper Session{C.RESET}  {C.DIM}— EEG → phase/gain modulation{C.RESET}"),
            ("2", f"{C.BOLD}Direct Actuator Bridge{C.RESET}   {C.DIM}— EEG → ESP32 vibration{C.RESET}"),
            ("3", f"{C.BOLD}Harmonic Series Bridge{C.RESET}  {C.DIM}— EEG → Surge XT + ESP32{C.RESET}"),
            ("---", ""),
            ("4", f"Utilities {C.DIM}(simulators, MIDI ports, tests){C.RESET}"),
            ("5", f"Architecture overview"),
            ("---", ""),
            ("q", "Quit"),
        ], back=False, quit_opt=True)

        if choice == "q" or choice is None:
            print(f"\n  {C.DIM}Goodbye.{C.RESET}\n")
            break
        elif choice == "1":
            wizard_shaper()
        elif choice == "2":
            wizard_actuator()
        elif choice == "3":
            wizard_harmonic()
        elif choice == "4":
            wizard_utilities()
        elif choice == "5":
            show_architecture()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {C.DIM}Interrupted.{C.RESET}\n")
