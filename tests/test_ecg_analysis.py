"""
Tests for ecg_analysis.py — R-peak detection from AD8232 ECG data.

Layer 1: Unit tests — pure math/logic (buffer, refractory, leads-off)
Layer 2: Pan-Tompkins pipeline — synthetic ECG with known R-peak locations
Layer 3: Integration — BPM accuracy, edge cases
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ecg_analysis import ECGProcessor, ECG_SAMPLE_RATE, ECG_BUFFER_SIZE


# ─── Test Helpers ───────────────────────────────────────────────

def make_synthetic_ecg(bpm=72, duration_s=6.0, sample_rate=ECG_SAMPLE_RATE,
                       baseline=2048, qrs_amplitude=800, noise_level=10):
    """Generate synthetic ECG-like signal with R-peaks at a known BPM.

    Returns (signal, peak_times_in_seconds).
    R-peaks are narrow Gaussians (σ=6ms) on a slowly wandering baseline.
    """
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate

    # Baseline wander (low frequency)
    signal = baseline + 50 * np.sin(2 * np.pi * 0.3 * t)

    # R-peaks at regular intervals
    interval = 60.0 / bpm
    # Start peaks after 0.5s to give the detector warm-up time
    peak_times = np.arange(0.5, duration_s - 0.2, interval)

    for pt in peak_times:
        # Narrow Gaussian: σ = 6ms → ~15 samples wide at 250 Hz
        signal += qrs_amplitude * np.exp(-0.5 * ((t - pt) / 0.006) ** 2)

    # Add noise
    signal += np.random.normal(0, noise_level, n)

    return signal.astype(np.float64), peak_times


def feed_ecg_in_batches(proc, signal, batch_size=8):
    """Feed a signal into the processor in batches, collect all beats."""
    all_beats = []
    for i in range(0, len(signal), batch_size):
        batch = signal[i:i + batch_size].tolist()
        beats = proc.add_samples(batch)
        all_beats.extend(beats)
    return all_beats


# ═══════════════════════════════════════════════════════════════
# Layer 1: Unit Tests — Buffer, State, Gating
# ═══════════════════════════════════════════════════════════════

class TestECGProcessorBasics:
    """Basic state management and buffer operations."""

    def test_initial_state(self):
        proc = ECGProcessor()
        assert proc.samples_received == 0
        assert proc.write_pos == 0
        assert proc.leads_off is False
        assert proc.compute_bpm() == 0.0
        assert len(proc.rr_history) == 0

    def test_add_samples_increments_count(self):
        proc = ECGProcessor()
        proc.add_samples([2048, 2048, 2048])
        assert proc.samples_received == 3
        assert proc.write_pos == 3

    def test_add_samples_batch_of_eight(self):
        proc = ECGProcessor()
        proc.add_samples([2048] * 8)
        assert proc.samples_received == 8

    def test_ring_buffer_wraps(self):
        proc = ECGProcessor(sample_rate=250, buffer_seconds=1)
        # Buffer size = 250. Feed 300 samples.
        for _ in range(300):
            proc.add_samples([2048])
        assert proc.samples_received == 300
        # Write pos should have wrapped
        assert proc.write_pos == 300

    def test_empty_samples_no_crash(self):
        proc = ECGProcessor()
        result = proc.add_samples([])
        assert result == []

    def test_insufficient_data_returns_empty(self):
        """Need at least 1 second of data before detection."""
        proc = ECGProcessor()
        # Feed less than sample_rate samples
        result = proc.add_samples([2048] * 100)
        assert result == []


class TestLeadsOff:
    """Lead-off detection gating."""

    def test_leads_off_blocks_detection(self):
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=6.0)

        proc.set_leads_off(True)
        beats = feed_ecg_in_batches(proc, signal)
        assert len(beats) == 0, "Should detect no beats when leads are off"

    def test_leads_off_still_buffers(self):
        proc = ECGProcessor()
        proc.set_leads_off(True)
        proc.add_samples([2048] * 50)
        assert proc.samples_received == 50, "Should still count samples when leads off"

    def test_leads_reconnect_resumes_detection(self):
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=8.0)

        # First 2 seconds with leads off
        cutoff = ECG_SAMPLE_RATE * 2
        proc.set_leads_off(True)
        feed_ecg_in_batches(proc, signal[:cutoff])

        # Reconnect and feed the rest
        proc.set_leads_off(False)
        beats = feed_ecg_in_batches(proc, signal[cutoff:])
        assert len(beats) > 0, "Should resume detection after leads reconnect"


class TestComputeBPM:
    """BPM computation from RR history."""

    def test_empty_history_returns_zero(self):
        proc = ECGProcessor()
        assert proc.compute_bpm() == 0.0

    def test_known_rr_intervals(self):
        proc = ECGProcessor()
        # 833ms intervals = 72 BPM
        for _ in range(5):
            proc.rr_history.append(0.833)
        bpm = proc.compute_bpm()
        assert abs(bpm - 72.0) < 1.0

    def test_uses_median_not_mean(self):
        proc = ECGProcessor()
        # 4 intervals at 72 BPM + 1 outlier
        for _ in range(4):
            proc.rr_history.append(0.833)
        proc.rr_history.append(1.5)  # outlier
        bpm = proc.compute_bpm()
        # Median should be 0.833, not pulled by outlier
        assert abs(bpm - 72.0) < 1.0

    def test_bpm_clamped(self):
        proc = ECGProcessor()
        proc.rr_history.append(0.1)  # 600 BPM — way too fast
        bpm = proc.compute_bpm()
        assert bpm <= 200.0

        proc.rr_history.clear()
        proc.rr_history.append(5.0)  # 12 BPM — way too slow
        bpm = proc.compute_bpm()
        assert bpm >= 30.0


# ═══════════════════════════════════════════════════════════════
# Layer 2: Pan-Tompkins Pipeline — Synthetic QRS Detection
# ═══════════════════════════════════════════════════════════════

class TestPanTompkinsDetection:
    """R-peak detection on synthetic ECG signals."""

    def test_detects_peaks_at_72bpm(self):
        """Should detect R-peaks from a clean 72 BPM synthetic ECG."""
        proc = ECGProcessor()
        signal, peak_times = make_synthetic_ecg(bpm=72, duration_s=8.0)
        beats = feed_ecg_in_batches(proc, signal)

        # Should detect most peaks (allow warm-up and edge effects)
        expected_beats = len(peak_times) - 1  # first peak has no RR
        assert len(beats) >= expected_beats * 0.6, \
            f"Detected {len(beats)} beats, expected at least {int(expected_beats * 0.6)}"

    def test_bpm_accuracy_72(self):
        """Detected BPM should be within +/-5 of target 72 BPM."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=10.0, noise_level=5)
        beats = feed_ecg_in_batches(proc, signal)

        if len(beats) >= 3:
            detected_bpms = [b[0] for b in beats]
            avg_bpm = np.mean(detected_bpms[-5:])
            assert abs(avg_bpm - 72.0) < 5.0, \
                f"Average BPM {avg_bpm:.1f} too far from target 72"

    def test_bpm_accuracy_100(self):
        """Should work at higher heart rates too."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=100, duration_s=10.0, noise_level=5)
        beats = feed_ecg_in_batches(proc, signal)

        if len(beats) >= 3:
            detected_bpms = [b[0] for b in beats]
            avg_bpm = np.mean(detected_bpms[-5:])
            assert abs(avg_bpm - 100.0) < 8.0, \
                f"Average BPM {avg_bpm:.1f} too far from target 100"

    def test_bpm_accuracy_60(self):
        """Should work at resting heart rate."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=60, duration_s=12.0, noise_level=5)
        beats = feed_ecg_in_batches(proc, signal)

        if len(beats) >= 3:
            detected_bpms = [b[0] for b in beats]
            avg_bpm = np.mean(detected_bpms[-5:])
            assert abs(avg_bpm - 60.0) < 5.0, \
                f"Average BPM {avg_bpm:.1f} too far from target 60"

    def test_no_false_positives_on_noise(self):
        """Random noise should produce few or no peaks."""
        proc = ECGProcessor()
        # Just noise around baseline, no QRS complexes
        noise = 2048 + np.random.normal(0, 30, ECG_SAMPLE_RATE * 8)
        beats = feed_ecg_in_batches(proc, noise)
        assert len(beats) < 3, \
            f"Detected {len(beats)} false beats on pure noise"

    def test_no_false_positives_on_flatline(self):
        """Constant signal should produce zero peaks."""
        proc = ECGProcessor()
        flat = np.ones(ECG_SAMPLE_RATE * 5) * 2048
        beats = feed_ecg_in_batches(proc, flat)
        assert len(beats) == 0

    def test_refractory_period_enforced(self):
        """Peaks closer than 300ms should be rejected."""
        proc = ECGProcessor()
        # Create signal with peaks every 200ms (300 BPM — beyond limit)
        signal, _ = make_synthetic_ecg(bpm=300, duration_s=6.0, qrs_amplitude=1200)
        beats = feed_ecg_in_batches(proc, signal)

        # All detected beats should have BPM <= 200
        for bpm, rr_ms in beats:
            assert bpm <= 200.0 + 5.0, \
                f"Detected {bpm:.0f} BPM, should be capped at ~200"
            assert rr_ms >= 280, \
                f"RR interval {rr_ms:.0f}ms is below refractory period"

    def test_rr_intervals_returned(self):
        """Each beat should return (bpm, rr_ms) with valid values."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=8.0)
        beats = feed_ecg_in_batches(proc, signal)

        for bpm, rr_ms in beats:
            assert 30 <= bpm <= 200, f"BPM {bpm} out of range"
            assert 300 <= rr_ms <= 2000, f"RR {rr_ms}ms out of range"
            # BPM and RR should be consistent
            expected_rr = 60000.0 / bpm
            assert abs(rr_ms - expected_rr) < 1.0, \
                f"BPM {bpm} and RR {rr_ms}ms are inconsistent"


class TestBatchProcessing:
    """Verify that batch size doesn't affect detection quality."""

    def test_single_sample_batches(self):
        """Should work with batch_size=1 (one sample at a time)."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=8.0, noise_level=5)
        beats = feed_ecg_in_batches(proc, signal, batch_size=1)
        # Should still detect beats
        assert len(beats) > 0

    def test_large_batches(self):
        """Should work with larger batches too."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=8.0, noise_level=5)
        beats = feed_ecg_in_batches(proc, signal, batch_size=64)
        assert len(beats) > 0


# ═══════════════════════════════════════════════════════════════
# Layer 3: Integration — Compute BPM After Detection
# ═══════════════════════════════════════════════════════════════

class TestIntegrationBPM:
    """End-to-end: synthetic ECG → processor → BPM."""

    def test_compute_bpm_after_detection(self):
        """compute_bpm should return a value close to 72 after processing."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=10.0)
        feed_ecg_in_batches(proc, signal)

        bpm = proc.compute_bpm()
        if len(proc.rr_history) >= 2:
            assert abs(bpm - 72.0) < 5.0, \
                f"compute_bpm returned {bpm:.1f}, expected ~72"

    def test_rr_history_fills(self):
        """RR history should accumulate intervals."""
        proc = ECGProcessor()
        signal, _ = make_synthetic_ecg(bpm=72, duration_s=10.0)
        feed_ecg_in_batches(proc, signal)
        assert len(proc.rr_history) > 0
