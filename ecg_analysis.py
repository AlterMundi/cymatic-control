"""
ECG Analysis — Real-time R-peak detection for AD8232 + ESP32 heart monitor.

Receives raw ECG samples (12-bit ADC values from ESP32) and detects R-peaks
using a simplified Pan-Tompkins pipeline. Designed to pair with hr_relay.py
in ECG mode: ESP32 streams /ecg/raw batches over WiFi OSC, this module
finds heartbeats, and hr_relay forwards /bridge/heartbeat to muse_bridge.

The processing chain:
  1. Bandpass filter 5-15 Hz (isolates QRS complex, removes P/T waves)
  2. Differentiate (emphasize steep slopes of R-peak)
  3. Square (make all values positive, amplify large slopes)
  4. Moving window integration (150 ms, smooths the squared signal)
  5. Adaptive threshold + refractory period (find_peaks)

Parallel to eeg_analysis.py — that module handles EEG band power extraction,
this one handles ECG R-peak detection. Both use numpy/scipy only.
"""

import numpy as np
from collections import deque
from scipy.signal import butter, sosfilt, sosfilt_zi, find_peaks


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

ECG_SAMPLE_RATE = 250       # Hz (must match ESP32 timer)
ECG_BUFFER_SECONDS = 4      # ring buffer duration
ECG_BUFFER_SIZE = ECG_SAMPLE_RATE * ECG_BUFFER_SECONDS  # 1000 samples

REFRACTORY_MS = 300         # minimum ms between R-peaks (200 BPM ceiling)
INTEGRATION_WINDOW_MS = 150 # Pan-Tompkins moving average window
DETECTION_INTERVAL = 0.25   # run peak detection every 250ms (not every batch)

BPM_MIN = 30.0
BPM_MAX = 200.0


# ─────────────────────────────────────────────
# Filter Design
# ─────────────────────────────────────────────

def design_ecg_bandpass(fs=ECG_SAMPLE_RATE, lowcut=5.0, highcut=15.0, order=2):
    """Butterworth bandpass for QRS complex isolation (Pan-Tompkins).

    5-15 Hz removes baseline wander, P-wave, T-wave, and high-frequency
    noise while preserving the steep slopes of the R-peak.
    """
    nyq = fs / 2.0
    sos = butter(order, [lowcut / nyq, highcut / nyq], btype="band", output="sos")
    return sos


# ─────────────────────────────────────────────
# ECG Processor
# ─────────────────────────────────────────────

class ECGProcessor:
    """Real-time R-peak detector for streaming ECG data.

    Maintains a ring buffer of raw ADC samples, applies the Pan-Tompkins
    pipeline on the full analysis window, and returns (bpm, rr_ms) tuples
    for each newly detected R-peak.

    Usage:
        proc = ECGProcessor(sample_rate=250)
        # ... on each batch from ESP32:
        beats = proc.add_samples([2048, 2100, 2950, ...])
        for bpm, rr_ms in beats:
            osc.send_message("/bridge/heartbeat", [bpm, rr_ms])
    """

    def __init__(self, sample_rate=ECG_SAMPLE_RATE, buffer_seconds=ECG_BUFFER_SECONDS):
        self.sample_rate = sample_rate
        self.buffer_size = int(sample_rate * buffer_seconds)
        self.buffer = np.zeros(self.buffer_size)
        self.write_pos = 0
        self.samples_received = 0

        # Pan-Tompkins bandpass filter (stateless — applied on full window)
        self.sos = design_ecg_bandpass(fs=sample_rate)

        # Integration window
        self._int_window = int(INTEGRATION_WINDOW_MS / 1000.0 * sample_rate)

        # Refractory period in samples
        self._refractory_samples = int(REFRACTORY_MS / 1000.0 * sample_rate)

        # Detection scheduling: run every N samples instead of every batch
        self._detect_interval = int(DETECTION_INTERVAL * sample_rate)
        self._samples_since_detect = 0

        # Peak detection state
        self.rr_history = deque(maxlen=8)  # recent RR intervals (in seconds)
        self._last_peak_pos = -1  # buffer-relative position of last peak
        self._last_peak_abs = -self._refractory_samples  # absolute sample #

        # Lead-off gating
        self.leads_off = False

    def _get_ordered_buffer(self):
        """Return the ring buffer as a contiguous array, oldest-first."""
        n = min(self.samples_received, self.buffer_size)
        wp = self.write_pos % self.buffer_size
        return np.roll(self.buffer, -wp)[:n].copy()

    def add_samples(self, samples):
        """Add a batch of raw ADC samples and detect R-peaks.

        Args:
            samples: list/array of raw 12-bit ADC values (0-4095)

        Returns:
            List of (bpm, rr_ms) tuples for each detected R-peak.
            Usually 0 or 1 per call.
        """
        if not samples:
            return []

        # Store in ring buffer
        for s in samples:
            self.buffer[self.write_pos % self.buffer_size] = float(s)
            self.write_pos += 1
            self.samples_received += 1

        if self.leads_off:
            return []

        self._samples_since_detect += len(samples)

        # Need at least 2 seconds of data before detection
        if self.samples_received < self.sample_rate * 2:
            return []

        # Only run detection every ~250ms (not on every 8-sample batch)
        if self._samples_since_detect < self._detect_interval:
            return []
        self._samples_since_detect = 0

        return self._detect_peaks()

    def _detect_peaks(self):
        """Run Pan-Tompkins on the full buffer and find new peaks."""
        signal = self._get_ordered_buffer()
        n = len(signal)

        # 1. Remove DC offset (AD8232 centers at ~VCC/2 ≈ 2048)
        #    Without this, the bandpass filter startup transient masks real peaks
        signal_centered = signal - np.mean(signal)

        # 2. Bandpass filter (offline on full window — no state issues)
        filtered = sosfilt(self.sos, signal_centered)

        # 2. Differentiate
        diff = np.diff(filtered, prepend=filtered[0])

        # 3. Square
        squared = diff ** 2

        # 4. Moving window integration
        kernel = np.ones(self._int_window) / self._int_window
        integrated = np.convolve(squared, kernel, mode="same")

        # 5. Signal quality check + adaptive threshold
        #    The integrated signal from a real QRS complex produces values
        #    orders of magnitude above noise. Require peaks to be both
        #    relatively tall (50% of max) and absolutely above the noise floor.
        peak_val = np.max(integrated)
        median_val = np.median(integrated)
        # SNR check: peak must be at least 5x the median (noise floor)
        if peak_val < 5.0 * max(median_val, 1e-10):
            return []
        threshold = 0.5 * peak_val

        # 6. Find peaks with refractory period and prominence
        peaks, _ = find_peaks(
            integrated,
            height=threshold,
            distance=self._refractory_samples,
            prominence=0.3 * peak_val,
        )

        if len(peaks) < 2:
            return []

        # Convert buffer-relative peak positions to absolute sample numbers
        # The buffer holds [oldest...newest], buffer position 0 = oldest sample
        buf_start_abs = self.samples_received - n

        beats = []
        for pk in peaks:
            abs_pos = buf_start_abs + pk

            # Skip peaks we've already reported
            if abs_pos <= self._last_peak_abs:
                continue

            # Enforce refractory period
            if abs_pos - self._last_peak_abs < self._refractory_samples:
                continue

            # Compute RR interval from previous peak
            if self._last_peak_abs > 0:
                rr_samples = abs_pos - self._last_peak_abs
                rr_seconds = rr_samples / self.sample_rate
                rr_ms = rr_seconds * 1000.0
                bpm = 60.0 / rr_seconds

                if BPM_MIN <= bpm <= BPM_MAX:
                    self.rr_history.append(rr_seconds)
                    self._last_peak_abs = abs_pos
                    beats.append((bpm, rr_ms))
                # If BPM is out of range, still update position to avoid
                # getting stuck on a noisy segment
                elif bpm > BPM_MAX:
                    self._last_peak_abs = abs_pos
            else:
                # First peak — record position, can't compute RR yet
                self._last_peak_abs = abs_pos

        return beats

    def compute_bpm(self):
        """Current BPM from median of recent RR intervals."""
        if not self.rr_history:
            return 0.0
        median_rr = float(np.median(list(self.rr_history)))
        if median_rr < 0.001:
            return 0.0
        bpm = 60.0 / median_rr
        return float(np.clip(bpm, BPM_MIN, BPM_MAX))

    def set_leads_off(self, off):
        """Gate detection based on electrode contact.

        When leads are off, add_samples still buffers data (to keep the
        ring buffer fresh) but returns no beats.
        """
        self.leads_off = bool(off)
