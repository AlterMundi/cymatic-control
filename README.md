# Cymatic Control

Live modulation of [harmonic_shaper](https://github.com/AlterMundi/NaturalHarmony)
cymatic patterns using EEG (Muse 2), heart rate (Fitbit / BLE), and MIDI
(Launchpad Mini). Every input is independent and optional.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start harmonic_shaper first (in the NaturalHarmony repo)
python -m harmonic_shaper.main

# Launch the interactive session builder
python cymatic.py
```

The interactive launcher walks you through a signal-chain wizard —
pick your inputs and the system figures out which scripts to run and
with what parameters:

```
Step 1/3 — EEG → Phase Rotation
  1  Muse 2 (live via Mind Monitor OSC)
  2  EEG Simulator (cycles through 7 brain states)
  3  Tilt Simulator (alpha/beta stages for gain observation)
  4  Skip (no EEG — heartbeat pulse only)

Step 2/3 — Heart Rate → Gain Pulse
  1  Skip (no heartbeat pulse)
  2  Simulate (synthetic beats at configurable BPM)
  3  BLE sensor (Fitbit Charge 6 / any BLE HR device)
  4  Fitbit Web API (cloud polling, OAuth required)

Step 3/3 — MIDI → Gain Tilt Depth
  1  Skip (no gain modulation)
  2  MIDI controller (Launchpad slider controls depth live)
  3  Fixed depth (constant EEG gain modulation, no slider)
```

Quick-start presets are also available — "test without hardware",
"Muse-only phase", and "full session" — each one launches all the
right processes with a single confirmation.

### Manual Launch

You can also run scripts directly if you prefer:

```bash
# Test without any hardware
python simulate_eeg.py &
python hr_relay.py --mode simulate --bpm 72 &
python muse_bridge.py --param both --depth 30

# Muse phase only
python muse_bridge.py --param phase --depth 30

# Muse + Launchpad + Fitbit (all three inputs)
python midi_relay.py --target-port 5000 &
python hr_relay.py --mode ble &
python muse_bridge.py --param both --depth 30
```

See [docs/SESSION_GUIDE.md](docs/SESSION_GUIDE.md) for all 7 configurations.

## Architecture

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

### Signal Chain (how inputs map to effects)

| Input | Script | What it controls | Effect on cymatics |
|-------|--------|------------------|--------------------|
| **Muse 2 EEG** | `muse_bridge.py` | Phase rotation | Shape of interference pattern evolves with brain state |
| **Muse 2 EEG** | `muse_bridge.py` | Gain tilt | Harmonic balance shifts (relaxed = warm, focused = bright) |
| **Fitbit / HR sensor** | `hr_relay.py` | Gain pulse | Visible "breathing" in sync with heartbeat |
| **Launchpad slider** | `midi_relay.py` | Gain tilt depth | How much EEG is allowed to tilt the gain curve |
| **EEG simulator** | `simulate_eeg.py` | Synthetic Muse 2 data | Replaces hardware for testing |

## Parameter Modes (`--param`)

| Mode | Phase from EEG? | Gain tilt from EEG? | Heartbeat pulse? |
|------|----------------|---------------------|-------------------|
| `phase` | Yes | No | Yes (if hr_relay running) |
| `gain` | No | Yes | Yes (if hr_relay running) |
| `both` | Yes | Yes | Yes (if hr_relay running) |

## HR Relay Modes (`hr_relay.py`)

| Mode | Hardware | Latency | Beat-accurate? |
|------|----------|---------|----------------|
| `simulate` | None | Zero | Synthetic |
| `ble` | Fitbit Charge 6 / BLE HR sensor | 50-200ms | Yes |
| `fitbit-api` | Any Fitbit (Web API) | 2-15 min | No (BPM synth) |

## Gain Formula

```
final_gain = base * (1 + tilt * gain_depth) * (1 + heartbeat_envelope)
```

- `base` = Launchpad-set gain (always respected)
- `tilt * gain_depth` = EEG influence (slider-controlled)
- `heartbeat_envelope` = pulse on each beat (0 at rest)

## Phase Rotation Mapping

| Harmonic | Sensor | Band | Effect |
|----------|--------|------|--------|
| H1 | --- | --- | Anchored (no rotation) |
| H2 | TP9 | theta | Rotation speed from theta power |
| H3 | AF7 | alpha | Rotation speed from alpha power |
| H4 | AF8 | beta | Rotation speed from beta power |
| H5 | TP10 | gamma | Rotation speed from gamma power |

## Scripts

| Script | Purpose |
|--------|---------|
| **`cymatic.py`** | **Interactive session launcher — the recommended entry point** |
| `muse_bridge.py` | EEG + heartbeat + slider -> harmonic_shaper modulation |
| `hr_relay.py` | Heart rate -> OSC (simulate, BLE, or Fitbit Web API) |
| `midi_relay.py` | MIDI CC (Launchpad slider) -> OSC for muse_bridge |
| `simulate_eeg.py` | Mock brain activity for testing (7 states) |
| `simulate_tilt.py` | Mock alpha/beta tilt stages for gain observation |
| `eeg_analysis.py` | Shared EEG signal processing (band power, PSD) |
| `osc_bridge.py` | Live Muse 2 -> actuator bridge (no harmonic_shaper) |
| `eeg_harmonic_bridge.py` | Live Muse 2 -> Surge XT + actuator |

## Testing

```bash
python -m pytest tests/ -v
```

48 tests covering gain tilt, phase rotation, heartbeat envelope, OSC handlers,
and end-to-end integration. No hardware required.

## Documentation

- [docs/SESSION_GUIDE.md](docs/SESSION_GUIDE.md) -- Modular architecture, all session configs
- [docs/PHASE_CONTROL_ANALYSIS.md](docs/PHASE_CONTROL_ANALYSIS.md) -- How EEG becomes phase rotation
- [docs/GAIN_MODULATION.md](docs/GAIN_MODULATION.md) -- Spectral tilt, slider, gain formula
- [docs/HEARTBEAT_PULSE.md](docs/HEARTBEAT_PULSE.md) -- Fitbit integration, envelope mechanics

## Related Projects

- [NaturalHarmony](https://github.com/AlterMundi/NaturalHarmony) -- harmonic_shaper synthesizer
- [BeaconMagnetActuator](https://github.com/Pablomonte/BeaconMagnetActuator) -- ESP32 harmonic surface
- [zuna-implemetation](../zuna-implemetation) -- ZUNA EEG denoising pipeline (batch processing)

## License

MIT
