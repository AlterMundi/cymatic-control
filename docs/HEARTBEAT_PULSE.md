# Heartbeat-Driven Cymatic Pulse

## Overview

A heart rate sensor (AD8232 chest ECG, Fitbit, or any BLE HR device) sends
beat timing to `muse_bridge.py`, which fires a short gain envelope on each
heartbeat.
The result is a visible rhythmic "breathing" in the cymatic pattern —
the figure swells and decays in sync with the performer's heartbeat.

The heartbeat is **fully optional**. If no `hr_relay.py` is running or
`--pulse 0` is set, the system works exactly as before — only EEG and
the Launchpad control the output.

---

## The Envelope

On each heartbeat, an exponential decay envelope fires:

```
envelope(t) = pulse_amplitude × exp(-t / decay_tau)
```

Where `t` is time since the last beat. The envelope starts at
`pulse_amplitude` (default 0.15 = 15% gain boost) and decays toward zero.

### Auto-Scaling Decay

The decay constant scales with BPM so pulses don't overlap:

```
decay_tau = 0.3 × (60 / bpm)
```

| BPM | Beat interval | decay_tau | Envelope at 50% of interval |
|-----|---------------|-----------|----------------------------|
| 60 | 1000 ms | 300 ms | 0.028 (1.9% of peak) |
| 72 | 833 ms | 250 ms | 0.027 (1.8% of peak) |
| 90 | 667 ms | 200 ms | 0.026 (1.7% of peak) |
| 120 | 500 ms | 150 ms | 0.027 (1.8% of peak) |

At all heart rates, the pulse has decayed to ~2% by the time the next beat
arrives — there's no "stacking" of pulses. Higher BPM simply means faster,
shorter pulses.

### How It Multiplies Into Gains

The pulse overlays on the existing gain chain:

```
final_gain = base × (1 + tilt × gain_depth) × (1 + envelope)
```

- `base` — Launchpad-set gain (always respected)
- `tilt × gain_depth` — EEG influence (slider-controlled, optional)
- `envelope` — heartbeat pulse (0 at rest, spikes on each beat)

The multiplication is per-harmonic. All harmonics swell together on each
beat, preserving the current tonal balance.

---

## Three Trigger Modes

The bridge supports three triggering modes, selected automatically based on
which OSC message it receives:

### Beat-Triggered Mode (BLE / Simulate)

`hr_relay.py` sends `/bridge/heartbeat [bpm, rr_ms]` on **each detected
beat**. The bridge resets `beat_phase` to 0 immediately, firing the
envelope. This gives beat-accurate timing — the cymatic pulse is
phase-locked to the actual heartbeat.

```
BLE sensor → hr_relay → /bridge/heartbeat → beat_phase = 0 → envelope fires
                                                 ↑
                                          on each physical beat
```

### BPM-Synthesized Mode (Fitbit Web API)

`hr_relay.py` sends `/bridge/heartbeat_bpm [bpm]` periodically (every
~15 seconds). The bridge runs a local clock at `60/bpm` seconds and
auto-triggers the envelope on each tick. The rhythm matches the person's
rate but isn't phase-locked to actual beats.

```
Web API → hr_relay → /bridge/heartbeat_bpm → bridge internal clock
                           (every ~15s)          → fires at 60/bpm interval
```

This is the fallback for Fitbit models that don't support BLE HR broadcast.

### ECG-Triggered Mode (AD8232 + ESP32)

`hr_relay.py` receives raw ECG samples from the ESP32 via `/ecg/raw` on
port 5001, runs Pan-Tompkins R-peak detection, and sends
`/bridge/heartbeat [bpm, rr_ms]` on each detected R-peak. This gives the
highest-fidelity beat timing — the cymatic pulse is phase-locked to the
actual QRS complex with single-digit millisecond latency from ADC read
to peak detection.

```
AD8232 → ESP32 ADC (250 Hz) → WiFi/OSC /ecg/raw :5001
    → hr_relay → Pan-Tompkins → /bridge/heartbeat → muse_bridge
```

---

## hr_relay.py: Four Modes

> **Tip:** The interactive launcher (`python cymatic.py`) handles heart rate
> setup in Step 2/3 of the signal-chain wizard — pick your source and it
> configures the relay and bridge automatically.

The relay script is the single entry point for all heart rate data sources.
It normalizes everything into the same OSC interface that `muse_bridge.py`
expects.

### Simulate Mode (`--mode simulate`)

**No hardware needed.** Generates synthetic heartbeats at a configurable BPM
with optional random variation. For development, testing, and tuning the
pulse parameters.

```bash
python hr_relay.py --mode simulate --bpm 72 --variation 3
```

Sends `/bridge/heartbeat [bpm, rr_ms]` on each synthetic beat. The
variation adds +/-N BPM random drift per beat, simulating natural heart
rate variability.

### BLE Mode (`--mode ble`)

**Fitbit Charge 6 or any standard BLE Heart Rate sensor** (chest straps,
smart watches that broadcast HR Profile UUID 0x180D).

```bash
python hr_relay.py --mode ble
python hr_relay.py --mode ble --device "Charge 6"
```

Uses `bleak` to scan for nearby BLE devices with the Heart Rate Service.
Subscribes to HR Measurement notifications (UUID 0x2A37). Extracts:

- Heart rate in BPM
- RR intervals (beat-to-beat timing in 1/1024 second resolution)

Sends `/bridge/heartbeat [bpm, rr_ms]` for each detected beat from the
RR interval data. This is the highest-fidelity path — ~50-200ms BLE
notification latency, beat-accurate.

**Fitbit Charge 6 setup:**
1. On the Charge 6, go to Settings > HR on Equipment > enable
2. Start an exercise (e.g. "Workout") on the watch
3. The Charge 6 now advertises as a standard BLE HR monitor
4. Run `hr_relay.py --mode ble` on the computer
5. The relay will find and connect to it automatically

**BLE Heart Rate Measurement Parsing:**

The BLE HR characteristic (0x2A37) encodes data in a compact binary format:

```
Byte 0: Flags
  bit 0: 0 = HR is uint8, 1 = HR is uint16
  bit 4: 0 = no RR intervals, 1 = RR intervals present

Byte 1 (or 1-2): Heart rate value
Remaining bytes: RR intervals (uint16, units of 1/1024 sec)
```

Most wrist sensors (including Charge 6) send 8-bit HR with RR intervals.
Chest straps may send 16-bit HR. The relay handles both formats.

### Fitbit Web API Mode (`--mode fitbit-api`)

**Any Fitbit model** — uses the Fitbit Web API to poll intraday heart rate
at 1-second resolution. Requires a Fitbit developer account and OAuth2 setup.

```bash
python hr_relay.py --mode fitbit-api \
    --client-id YOUR_CLIENT_ID \
    --client-secret YOUR_CLIENT_SECRET \
    --poll-interval 15
```

**One-time setup:**
1. Register an app at https://dev.fitbit.com/apps/new
   - OAuth 2.0 Application Type: "Personal"
   - Callback URL: `http://localhost:8189/callback`
   - Access type: Read-only
2. Copy the Client ID and Client Secret
3. Run the relay — it will print a URL to open in your browser
4. Authorize the app, paste the redirect URL back
5. Token is saved to `~/.fitbit_token.json` (auto-refreshes)

**Limitations:**
- Intraday data has 2-15 minute cloud sync delay
- No RR intervals, only BPM values
- The bridge synthesizes beats locally from BPM (rhythmically correct
  but not phase-locked to actual beats)

Sends `/bridge/heartbeat_bpm [bpm]` on each poll.

### ECG Mode (`--mode ecg`)

**AD8232 + ESP32** — the highest-fidelity heartbeat source. The AD8232
single-lead ECG monitor captures the raw cardiac waveform from chest
electrodes. The ESP32 samples the analog output at 250 Hz and streams
batches of 8 samples over WiFi as OSC to `hr_relay.py`, which runs a
Pan-Tompkins R-peak detection pipeline and forwards beat events.

```bash
python hr_relay.py --mode ecg --ecg-listen-port 5001
```

**Hardware setup:**

```
AD8232 Pin    NodeMCU ESP-32S    Notes
──────────    ────────────────   ─────
OUTPUT        IO34 (GPIO 34)     ADC1_CH6, input-only (clean analog read)
LO+           IO32 (GPIO 32)     Lead-off detect (digital)
LO-           IO33 (GPIO 33)     Lead-off detect (digital)
3.3V          3V3                AD8232 runs at 3.3V natively
GND           GND                Common ground
SDN           (float/3.3V)       LOW = shutdown, leave floating for normal
```

All three signal pins are on ADC1 (GPIO 32-39), which is safe to use
alongside WiFi (ADC2 is disabled when WiFi is active).

**Electrode placement (3-lead chest):**
- **RA** (right arm, black): Right chest, below collarbone
- **LA** (left arm, red/blue): Left chest, below collarbone, symmetric
- **RL** (right leg, green): Lower right abdomen (reference/ground)

All electrodes under clothing for a performer. Chest placement minimizes
motion artifact compared to limb placement.

**ESP32 firmware:**

See `firmware/ecg_esp32/ecg_esp32.ino`. No external libraries needed
beyond the ESP32 core — OSC is implemented inline using raw UDP.

**Configuration (two options):**
- **Edit defaults:** Change the `DEFAULT_SSID`, `DEFAULT_PASS`,
  `DEFAULT_TARGET_IP` values at the top of the file and re-upload.
- **Serial commands:** Connect at 115200 baud and type:
  ```
  ssid:YourNetwork
  pass:YourPassword
  ip:192.168.1.100
  port:5001
  save
  ```
  Settings are saved to flash and persist across reboots. Type `status`
  anytime to see the current config.

**Testing the stream:**

Use `test_ecg_stream.py` to verify the ESP32 is sending data before
running the full cymatic system:

```bash
python test_ecg_stream.py          # signal trace + packet rate
python test_ecg_stream.py --detect  # also runs R-peak detection, shows BPM
python test_devices.py --ecg       # combined device monitor (works for EEG too)
```

**Signal processing (Pan-Tompkins pipeline):**
1. Bandpass filter 5-15 Hz (isolates QRS, removes P/T waves)
2. Differentiate (emphasize R-peak slopes)
3. Square (amplify large slopes, make positive)
4. Moving window integration (150 ms smoothing)
5. Adaptive threshold + refractory period (300 ms = 200 BPM max)

Sends `/bridge/heartbeat [bpm, rr_ms]` on each detected R-peak — same
message as BLE and simulate modes. `muse_bridge.py` needs no changes.

**Lead-off detection:** When the ESP32 detects electrode disconnection
(LO+/LO- pins go HIGH), it sends `/ecg/leads_off [1]` and the relay
stops forwarding beats until contact is restored.

---

## Which Device Should You Use?

| Device | Real-time? | Recommended Mode |
|--------|------------|------------------|
| **AD8232 + ESP32** | Yes (ECG, ~5ms latency) | `--mode ecg` (best fidelity) |
| **Charge 6** | Yes (BLE, ~50-200ms) | `--mode ble` |
| **Any BLE chest strap** | Yes (always on) | `--mode ble` |
| Sense 2 / Versa 4 | No (cloud delay) | `--mode fitbit-api` |
| Inspire 3 / Luxe | No (cloud delay) | `--mode fitbit-api` |
| No device yet | N/A | `--mode simulate` |

---

## Visual Effect on Cymatics

### What You See

On each heartbeat, all harmonics swell in gain simultaneously:

```
  gain
  1.0 ┤
      │     ╱╲          ╱╲          ╱╲
  0.9 ┤    ╱  ╲        ╱  ╲        ╱  ╲
      │   ╱    ╲      ╱    ╲      ╱    ╲
  0.8 ┤──╱──────╲────╱──────╲────╱──────╲──── base gain
      │          ╲  ╱          ╲  ╱
  0.7 ┤           ╲╱            ╲╱
      │
      └──────────────────────────────────── time
           beat 1      beat 2      beat 3
```

On the cymatic mirror, this creates a rhythmic pulse in the overall
figure intensity. The pattern briefly becomes more defined (higher amplitude
= stronger standing wave = clearer interference pattern), then relaxes.

### Combined with EEG

The heartbeat pulse is multiplicative on top of any EEG gain tilt. If the
EEG is tilting gains toward upper harmonics (focused state), the heartbeat
pulse swells those already-boosted harmonics even further. The two effects
layer naturally:

- **EEG** controls the *balance* between harmonics (slow, brain-state-driven)
- **Heartbeat** creates a *rhythmic pulse* across all harmonics (fast, body-driven)

### Combined with Phase

When running alongside phase rotation, the heartbeat pulse adds a third
dimension to the cymatic evolution:

- **Phase** (Muse 2): The *shape* of the interference pattern slowly evolves
- **Gain tilt** (Muse 2 + slider): The *tonal balance* shifts with brain state
- **Gain pulse** (AD8232 / Fitbit): The *intensity* rhythmically breathes with the heart

---

## Configuration

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--pulse 0.15` | 0.15 | Heartbeat pulse amplitude (0 = disabled) |

### OSC Messages (received by muse_bridge)

| Address | Payload | Source | Effect |
|---------|---------|--------|--------|
| `/bridge/heartbeat` | `[bpm, rr_ms]` | BLE / simulate / ECG | Fires envelope immediately |
| `/bridge/heartbeat_bpm` | `[bpm]` | Fitbit Web API | Updates local beat synthesizer |

### Tuning the Pulse

| pulse_amplitude | Effect |
|-----------------|--------|
| 0.0 | Disabled (no heartbeat effect) |
| 0.05 | Very subtle, barely visible |
| **0.15** | **Default — clear but not overwhelming** |
| 0.25 | Strong, prominent breathing |
| 0.40 | Very dramatic, may clip gains near 1.0 |

The decay shape cannot be tuned directly from CLI — it auto-scales with BPM.
If you need different envelope shapes, modify the `compute_heartbeat_envelope`
method in `muse_bridge.py`.

### Dependencies

| Package | Mode | Install |
|---------|------|---------|
| `bleak>=0.22.0` | BLE | `pip install bleak` |
| `requests-oauthlib>=1.3.0` | fitbit-api | `pip install requests-oauthlib` |
| (none extra) | simulate | Already in requirements |
| (none extra) | ecg | Uses numpy/scipy already in requirements |
