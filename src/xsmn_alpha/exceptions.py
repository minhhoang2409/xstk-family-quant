"""Fail-Closed exception hierarchy for the 4 Adversarial Gates in Stage 2 XSMN Alpha Discovery."""

from __future__ import annotations


class XSMNAlphaError(Exception):
    """Base exception for all fail-closed errors in the XSMN Stage 2 Alpha Discovery system."""


class DataIntegrityError(XSMNAlphaError):
    """Raised by Gate 1 (DataSchemaGate) when draw records or schema contracts are violated."""


class TemporalLeakageError(XSMNAlphaError):
    """Raised by Gate 2 (PreDrawCutoffGate) on look-ahead or intra-draw temporal leakage."""


class CalibrationIntegrityError(XSMNAlphaError):
    """Raised by Gate 3 (SimplexCalibrationGate) on probability simplex or weight violations."""


class InsufficientSampleSizeError(XSMNAlphaError):
    """Raised by Gate 4 (FalsificationGatekeeper) when sample size is below minimum threshold."""


class CapitalDisciplineError(XSMNAlphaError):
    """Raised by Gate 5 (HouseMoneyAndLedgerIntegrityGate) on sizing or ledger violations."""
