"""Shared pytest fixtures for Stage 2 XSMN Alpha Discovery test suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_valid_prizes_18() -> list[str]:
    """Return a valid 18-prize list of 2-digit ASCII strings (Giải 8 -> Giải ĐB)."""
    return [
        "42",
        "18",
        "73",
        "08",
        "83",
        "39",
        "88",
        "14",
        "57",
        "81",
        "23",
        "90",
        "38",
        "84",
        "61",
        "03",
        "78",
        "83",
    ]


@pytest.fixture
def sample_valid_tens_counts() -> list[int]:
    """Return the exact 10-ball tens cage count vector for sample_valid_prizes_18."""
    return [2, 2, 1, 2, 1, 1, 1, 2, 5, 1]


@pytest.fixture
def sample_valid_units_counts() -> list[int]:
    """Return the exact 10-ball units cage count vector for sample_valid_prizes_18."""
    return [1, 2, 1, 5, 2, 0, 0, 1, 5, 1]
