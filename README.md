# Cymatic Control

Live modulation of [harmonic_shaper](https://github.com/AlterMundi/NaturalHarmony)
cymatic patterns using EEG (Muse 2), heart rate (Fitbit / BLE), and MIDI
(Launchpad Mini). Every input is independent and optional.

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

### Modular Inputs

| Input | Script | Controls | Optional? |
|-------|--------|----------|-----------|
| **Muse 2 EEG** | `muse_bridge.py` | Phase rotation + gain tilt | Yes |
| **Fitbit / HR sensor** | `hr_relay.py` | Heartbeat gain pulse | Yes |
| **Launchpad slider** | `midi_relay.py` | EEG gain modulation depth | Yes |
| **EEG simulator** | `simulate_eeg.py` | Synthetic Muse 2 data | Replaces hardware |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start harmonic_shaper first (in the NaturalHarmony repo)
python -m harmonic_shaper.main
```

### Session Configurations

**1. Muse phase only** -- brain rhythms control cymatic shape
```bash
python muse_bridge.py --param phase --depth 30
```

**2. Muse phase + Fitbit heartbeat** -- shape from brain, pulse from heart
```bash
python hr_relay.py --mode simulate --bpm 72 &
python muse_bridge.py --param phase --depth 30
```

**3. Muse + Launchpad + Fitbit** -- all three inputs
```bash
python midi_relay.py --target-port 5000 &
python hr_relay.py --mode ble &
python muse_bridge.py --param both --depth 30
```

**4. Test without any hardware**
```bash
python simulate_eeg.py &
python hr_relay.py --mode simulate --bpm 72 &
python muse_bridge.py --param both --depth 30
```

See [docs/SESSION_GUIDE.md](docs/SESSION_GUIDE.md) for all 7 configurations.

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
