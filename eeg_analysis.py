"""
EEG Analysis Helpers — Shared signal processing for EEG band power extraction.

Provides frequency band definitions and Welch PSD-based band power
computation used by muse_bridge, osc_bridge, and eeg_harmonic_bridge.
"""

import numpy as np
from scipy.signal import welch


BANDS = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "smr":   (12, 15),
    "beta":  (13, 30),
    "gamma": (30, 44),
}

CONCENTRATION_WEIGHTS = {
    "beta_alpha": 0.5,
    "smr": 0.3,
    "inv_theta_beta": 0.2,
}


def compute_band_powers(signal_data, sfreq):
    """Compute power for each EEG frequency band using Welch PSD."""
    powers = {}
    for band_name, (low, high) in BANDS.items():
        if len(signal_data) < sfreq:
            powers[band_name] = 0.0
            continue
        freqs, psd = welch(signal_data, fs=sfreq, nperseg=min(len(signal_data), int(sfreq * 2)))
        band_idx = (freqs >= low) & (freqs <= high)
        powers[band_name] = float(np.mean(psd[band_idx])) if np.any(band_idx) else 0.0
    return powers


def find_dominant_frequency(signal_data, sfreq, fmin=0.5, fmax=44.0):
    """Find the dominant frequency in the EEG signal."""
    if len(signal_data) < sfreq:
        return 10.0, 0.0
    freqs, psd = welch(signal_data, fs=sfreq, nperseg=min(len(signal_data), int(sfreq * 2)))
    mask = (freqs >= fmin) & (freqs <= fmax)
    if not np.any(mask):
        return 10.0, 0.0
    peak_idx = np.argmax(psd[mask])
    peak_freq = freqs[mask][peak_idx]
    peak_power = psd[mask][peak_idx]
    return float(peak_freq), float(peak_power)


def compute_concentration(band_powers):
    """Compute concentration score (0-100) from band powers."""
    alpha = band_powers.get("alpha", 1e-10) + 1e-10
    beta = band_powers.get("beta", 1e-10) + 1e-10
    theta = band_powers.get("theta", 1e-10) + 1e-10
    smr = band_powers.get("smr", 1e-10) + 1e-10

    beta_alpha_ratio = beta / alpha
    smr_power = smr
    inv_theta_beta = beta / theta

    score = (
        CONCENTRATION_WEIGHTS["beta_alpha"] * min(beta_alpha_ratio / 2.0, 1.0) +
        CONCENTRATION_WEIGHTS["smr"] * min(smr_power / 50.0, 1.0) +
        CONCENTRATION_WEIGHTS["inv_theta_beta"] * min(inv_theta_beta / 3.0, 1.0)
    ) * 100
    return float(np.clip(score, 0, 100))


def map_to_velocity(value, vmin, vmax, out_min=0, out_max=127):
    """Map a value from [vmin, vmax] to [out_min, out_max]."""
    if vmax <= vmin:
        return out_min
    normalized = (value - vmin) / (vmax - vmin)
    normalized = np.clip(normalized, 0.0, 1.0)
    return float(out_min + normalized * (out_max - out_min))


def clamp_frequency(freq, fmin=20.0, fmax=2000.0):
    """Clamp frequency to actuator range."""
    return float(np.clip(freq, fmin, fmax))
