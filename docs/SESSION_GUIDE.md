# Session Guide: Modular Architecture

## Interactive Launcher (recommended)

The easiest way to set up any session is the interactive launcher:

```bash
python cymatic.py
```

It walks you through a signal-chain wizard — pick your inputs and the system
determines the correct scripts, flags, and parameter mode automatically:

| Step | Signal → Effect | What you choose |
|------|-----------------|-----------------|
| 1/3 | **EEG → Phase rotation** | Muse 2, EEG Simulator, Tilt Simulator, or skip |
| 2/3 | **Heart Rate → Gain pulse** | Simulate, BLE sensor, Fitbit Web API, or skip |
| 3/3 | **MIDI → Gain tilt depth** | MIDI controller, fixed depth, or skip |

The launcher resolves the `--param` mode from your choices:

| Inputs selected | Resolved mode |
|-----------------|---------------|
| EEG only | `phase` |
| EEG + MIDI slider | `both` (phase + gain) |
| EEG + fixed gain depth | `both` (phase + gain) |
| HR only (no EEG) | `phase --depth 0` (pulse only) |
| EEG + HR (no MIDI) | `phase` with pulse |
| EEG + HR + MIDI | `both` with pulse |

After configuring, it shows a preview of every command it will run
and launches all processes with proper sequencing (background relays first,
main bridge last). Ctrl+C stops everything cleanly.

Quick-start presets are also available: **Test without hardware**,
**Muse-only phase**, and **Full session** (Muse + Launchpad + BLE HR).

---

## Core Principle

**Every input is independent and optional.** The system is built so you can
use any combination of Muse 2, Fitbit, and Launchpad — or none of them —
and the bridge handles it gracefully. No input source depends on any other.

| Input | Script | What it controls | If absent |
|-------|--------|------------------|-----------|
| Muse 2 EEG | (streams to `muse_bridge.py`) | Phase rotation + gain tilt | Bridge idles, no modulation |
| Fitbit / HR sensor | `hr_relay.py` | Gain pulse on heartbeat | No pulse, gains stay flat |
| Launchpad slider | `midi_relay.py` | EEG gain modulation depth | Depth stays at CLI default |
| EEG simulator | `simulate_eeg.py` | Synthetic Muse 2 data | Replaces Muse 2 hardware |

---

## The Full Signal Chain

```
                         ┌─────────────────────────────────┐
  Muse 2 ──OSC──────────→│                                 │
  (or simulate_eeg.py)   │                                 │
                         │         muse_bridge.py          │
  Fitbit ──hr_relay.py──→│                                 │──→ harmonic_shaper
                         │  param mode: gain/phase/both    │    (OSC :9002)
  Launchpad ──midi_relay→│                                 │
                    .py  │                                 │
                         └─────────────────────────────────┘
```

**What muse_bridge.py sends to harmonic_shaper:**

| Parameter | When sent | Driven by |
|-----------|-----------|-----------|
| `/shaper/harmonic/N/phase` | Phase or both mode | Muse 2 band power |
| `/shaper/harmonic/N/gain` | Gain or both mode, or heartbeat active | EEG tilt × slider depth × heartbeat pulse |

---

## Session Configurations

> **Tip:** All of these configurations can be set up through the interactive
> launcher (`python cymatic.py`) without memorizing any flags. The manual
> commands below are useful for scripting or understanding what runs under
> the hood.

### 1. Muse Phase Only

The simplest EEG session. Brain rhythms control the cymatic interference
pattern through continuous phase rotation.

```bash
python muse_bridge.py --param phase --depth 30
```

**What happens:**
- Phase rotates based on band power (theta→H2, alpha→H3, beta→H4, gamma→H5)
- Gains stay at Launchpad-set values (no modulation)
- Output at 30 Hz for smooth cymatic movement

**Good for:** Exploring the relationship between brain states and cymatic
shapes. Meditative sessions. Phase-only art installations.

### 2. Muse Gain Only

Brain states tilt the harmonic balance.

```bash
python muse_bridge.py --param gain --depth 0.20
```

**What happens:**
- Alpha/beta ratio tilts gains across the harmonic series
- Relaxation emphasizes upper harmonics, focus emphasizes lower
- Phase stays fixed at Launchpad-set values

**Good for:** Exploring tonal balance shifts without shape changes.

### 3. Muse Phase + Launchpad Gain

The full EEG experience with manual gain depth control.

```bash
# Terminal 1: MIDI relay
python midi_relay.py --target-port 5000

# Terminal 2: Bridge
python muse_bridge.py --param both --depth 30
```

**What happens:**
- Phase rotates from Muse band power
- Gain tilts from Muse alpha/beta ratio
- Slider at 0% = no gain tilt (phase only)
- Slider at 100% = maximum EEG gain influence
- Performer can blend gain influence in/out during the session

**Good for:** Live performance. The slider gives real-time creative control
over how much the brain affects the tonal balance.

### 4. Muse Phase + Fitbit Gain Pulse

Brain controls the shape, heart controls the intensity.

```bash
# Terminal 1: HR relay (simulated or real)
python hr_relay.py --mode simulate --bpm 72

# Terminal 2: Bridge
python muse_bridge.py --param phase --depth 30
```

**What happens:**
- Phase rotates from Muse band power (brain-driven shape)
- On each heartbeat, all gains swell and decay (body-driven breathing)
- No EEG gain tilt (slider not needed)
- The cymatic pattern evolves (phase) and breathes (pulse) simultaneously

**Good for:** Body-brain feedback sessions. The visual connection between
heartbeat and cymatic movement creates a powerful biofeedback loop.

### 5. All Three: Muse + Launchpad + Fitbit

Maximum input — brain, body, and manual control.

```bash
# Terminal 1
python midi_relay.py --target-port 5000

# Terminal 2
python hr_relay.py --mode ble

# Terminal 3
python muse_bridge.py --param both --depth 30
```

**What happens:**
- Phase rotates from Muse (shape evolves)
- Gain tilts from Muse alpha/beta (tonal balance shifts)
- Slider controls how much EEG affects gain (performer control)
- Heartbeat pulse overlays on everything (rhythmic breathing)

**Gain formula at work:**
```
final_gain = base × (1 + tilt × slider_depth) × (1 + heartbeat_envelope)
```

### 6. Fitbit Pulse Only

No Muse, no Launchpad — heartbeat is the only modulation source.

```bash
# Terminal 1
python hr_relay.py --mode simulate --bpm 72

# Terminal 2
python muse_bridge.py --param phase --depth 0
```

**What happens:**
- `--depth 0` means no phase rotation from EEG (even if Muse is streaming)
- The heartbeat pulse is the only thing modulating gains
- The cymatic pattern breathes in sync with the heart
- Phase stays fixed at Launchpad-set values

**Good for:** Testing the heartbeat feature in isolation. Heart-only
biofeedback sessions.

### 7. Full Hardware-Free Test

No Muse, no Fitbit, no Launchpad — all simulated.

```bash
# Terminal 1: Synthetic EEG
python simulate_eeg.py

# Terminal 2: Synthetic heartbeat
python hr_relay.py --mode simulate --bpm 72 --variation 5

# Terminal 3: Bridge
python muse_bridge.py --param both --depth 30
```

**What happens:**
- `simulate_eeg.py` generates cycling brain states (alpha→beta→theta→gamma)
- `hr_relay.py` generates beats at ~72 BPM with random variation
- The bridge processes both as if they were real
- Full visual output to harmonic_shaper

**Good for:** Development, debugging, tuning parameters before a live session.

---

## How Inputs Combine

### Independence

Each input operates on its own axis:

```
                    ┌─────────────────────────────────────────────────┐
                    │               harmonic_shaper                   │
                    │                                                 │
  Muse EEG ───────→│  phase rotation  (shape of interference)        │
                    │                                                 │
  Muse EEG ───────→│  gain tilt       (harmonic balance)             │
                    │       ↕                                         │
  Launchpad ──────→│  gain depth      (how much EEG affects gain)    │
                    │       ↕                                         │
  Fitbit ─────────→│  gain pulse      (rhythmic intensity swell)     │
                    │                                                 │
  Launchpad ──────→│  base gains      (always respected)             │
  (harmonic_beacon) │  base phases     (always respected)             │
                    └─────────────────────────────────────────────────┘
```

### Priority

Base values set by the Launchpad (via harmonic_beacon) are **always respected**.
The EEG and heartbeat modulate *around* the base values, never replacing them.
If the performer sets H3 to gain=0.6, the system guarantees H3 stays centered
around 0.6 regardless of brain state or heart rate.

### Shutdown

When muse_bridge exits (Ctrl+C), it restores all modified parameters to their
base values. Gains and phases return to exactly what the performer set before
the bridge started. The harmonic_shaper is left in a clean state.

---

## Quick Reference: Which `--param` Mode?

| Mode | Phase from EEG? | Gain tilt from EEG? | Heartbeat pulse? | Slider controls? |
|------|----------------|---------------------|-------------------|------------------|
| `--param phase` | Yes | No | Yes (if hr_relay running) | N/A |
| `--param gain` | No | Yes | Yes (if hr_relay running) | gain_depth |
| `--param both` | Yes | Yes | Yes (if hr_relay running) | gain_depth |

The heartbeat pulse works in **all modes** — it modifies gains regardless of
whether EEG gain tilt is active.

---

## Port Map

All communication happens over OSC (UDP) on localhost by default:

| Port | Service | Direction |
|------|---------|-----------|
| **5000** | muse_bridge listens | IN: Muse 2 EEG, hr_relay heartbeat, midi_relay slider |
| **9001** | harmonic_beacon listens | IN: from harmonic_shaper (not used by bridge) |
| **9002** | harmonic_shaper listens | IN: phase/gain from muse_bridge, voices from beacon |
| **8080** | harmonic_shaper HTTP API | IN: state queries from muse_bridge on startup |

All scripts default to `127.0.0.1` (localhost). For multi-machine setups,
use the `--target-ip` / `--shaper-ip` arguments.

---

## Other Bridge Modes

The Harmonic Shaper session (muse_bridge) is the primary workflow, but two
standalone bridges are also available for different hardware setups:

| Bridge | Target | Use case |
|--------|--------|----------|
| `osc_bridge.py` | ESP32 actuator (OSC /fnote) | EEG → vibration without harmonic_shaper |
| `eeg_harmonic_bridge.py` | Surge XT + ESP32 (HTTP) | Multi-voice harmonic series with filter modulation |

Both are accessible through the interactive launcher's main menu (options 2
and 3), or can be run directly from the command line.

---

## Further Reading

- [PHASE_CONTROL_ANALYSIS.md](PHASE_CONTROL_ANALYSIS.md) — Deep dive into how EEG becomes phase rotation
- [GAIN_MODULATION.md](GAIN_MODULATION.md) — Spectral tilt, tilt weights, the gain formula
- [HEARTBEAT_PULSE.md](HEARTBEAT_PULSE.md) — Fitbit integration, hr_relay modes, envelope mechanics
