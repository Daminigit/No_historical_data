"""tests/test_emi.py — Unit tests for the EMI calculation."""
import pytest
from steps.read_project import compute_emi

# Default config values
_CFG = {"down_payment_pct": 20, "interest_rate_pct": 8.5, "tenure_years": 20}


def test_aurelia_2bhk_emi():
    """₹96 L at 20% down, 8.5% pa, 20 yr → ~₹67,000/mo (±₹500)."""
    emi = compute_emi(9_600_000, _CFG)
    assert 66_500 <= emi <= 67_500, f"Expected ~₹67,000, got ₹{emi:,.0f}"


def test_emi_decreases_with_higher_down_payment():
    """A higher down payment produces a lower EMI."""
    emi_20 = compute_emi(10_000_000, _CFG)
    emi_30 = compute_emi(10_000_000, {**_CFG, "down_payment_pct": 30})
    assert emi_30 < emi_20


def test_emi_increases_with_higher_rate():
    """A higher interest rate produces a higher EMI."""
    emi_low = compute_emi(10_000_000, _CFG)
    emi_high = compute_emi(10_000_000, {**_CFG, "interest_rate_pct": 10.0})
    assert emi_high > emi_low


def test_emi_positive():
    """EMI is always positive for any reasonable input."""
    assert compute_emi(5_000_000, _CFG) > 0


def test_emi_proportional_to_price():
    """Doubling the price roughly doubles the EMI."""
    emi_1 = compute_emi(5_000_000, _CFG)
    emi_2 = compute_emi(10_000_000, _CFG)
    assert abs(emi_2 - 2 * emi_1) < 10  # within ₹10 due to rounding
