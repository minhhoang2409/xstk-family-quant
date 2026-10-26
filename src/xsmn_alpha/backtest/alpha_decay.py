"""Pillar 4A: Out-of-Sample Rank-Ordered Alpha Decay Curve (Rank 1 -> Rank 10)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from xsmn_alpha.constants import CAGE_NUM_BALLS, PRIZES_PER_DRAW
from xsmn_alpha.exceptions import CalibrationIntegrityError, DataIntegrityError
from xsmn_alpha.schemas import (
    CalibratedCagePrediction,
    CanonicalDrawRecord,
    validate_probability_simplex,
    validate_two_digit_ascii,
)


def rank_balls_from_probabilities(probs: Sequence[float] | np.ndarray) -> list[int]:
    """Return a deterministic permutation of 0..9 ordered by probability descending."""
    if isinstance(probs, np.ndarray) and probs.dtype == np.bool_:
        raise CalibrationIntegrityError("Boolean ndarray cannot be ranked as probabilities.")
    clean_probs = validate_probability_simplex(
        probs.tolist() if isinstance(probs, np.ndarray) else probs,
        expected_len=CAGE_NUM_BALLS,
    )
    return sorted(range(CAGE_NUM_BALLS), key=lambda i: (-clean_probs[i], i))


rank_balls_by_probability = rank_balls_from_probabilities


def _extract_ranked_balls_from_pred(
    pred_item: Sequence[int] | np.ndarray | CalibratedCagePrediction,
    *,
    step_idx: int = 0,
) -> list[int]:
    """Extract and strictly validate a 0..9 ball permutation from prediction or sequence."""
    expected_set = set(range(CAGE_NUM_BALLS))
    if isinstance(pred_item, CalibratedCagePrediction):
        raw_ranks = pred_item.ranked_balls
        if not isinstance(raw_ranks, Sequence) or isinstance(raw_ranks, (str, bytes)):
            raise DataIntegrityError(f"Invalid ranked_balls at step {step_idx}.")
        ranks: list[int] = []
        for b in raw_ranks:
            if isinstance(b, bool) or not isinstance(b, (int, np.integer)):
                raise DataIntegrityError(
                    f"Ball index in ranked_balls at step {step_idx} must be strict int, got {b!r}."
                )
            ranks.append(int(b))
        if len(ranks) != CAGE_NUM_BALLS or set(ranks) != expected_set:
            raise DataIntegrityError(
                f"ranked_balls at step {step_idx} must be a permutation of 0..9, got {ranks}."
            )
        expected_ranks = rank_balls_from_probabilities(pred_item.p_ai)
        if ranks != expected_ranks:
            raise CalibrationIntegrityError(
                f"CalibratedCagePrediction.ranked_balls {ranks} at step {step_idx} "
                f"is inconsistent with p_ai ranking {expected_ranks}."
            )
        if (
            isinstance(pred_item.conviction_score, bool)
            or not isinstance(pred_item.conviction_score, (int, float))
            or float(pred_item.conviction_score) < 0.0
            or float(pred_item.conviction_score) > 100.0 + 1e-6
        ):
            raise CalibrationIntegrityError(
                f"CalibratedCagePrediction.conviction_score out of [0, 100]: "
                f"{pred_item.conviction_score!r}."
            )
        return ranks

    if isinstance(pred_item, np.ndarray):
        if pred_item.dtype == np.bool_ or pred_item.shape != (CAGE_NUM_BALLS,):
            raise DataIntegrityError(
                f"Invalid ranked_balls ndarray at step {step_idx}: "
                f"shape={pred_item.shape}, dtype={pred_item.dtype}."
            )
        seq: Sequence[Any] = pred_item.tolist()
    elif isinstance(pred_item, Sequence) and not isinstance(pred_item, (str, bytes)):
        seq = pred_item
    else:
        raise DataIntegrityError(
            f"Invalid prediction item at step {step_idx}: {type(pred_item).__name__}."
        )

    ranks = []
    for b in seq:
        if isinstance(b, bool) or not isinstance(b, (int, np.integer)):
            raise DataIntegrityError(
                f"Ball index at step {step_idx} must be strict int (not bool/float/str), got {b!r}."
            )
        ranks.append(int(b))
    if len(ranks) != CAGE_NUM_BALLS or set(ranks) != expected_set:
        raise DataIntegrityError(
            f"ranked_balls at step {step_idx} must be a permutation of 0..9, got {ranks}."
        )
    return ranks


def _extract_counts_from_actual(
    actual_item: Sequence[int] | np.ndarray | CanonicalDrawRecord,
    *,
    cage_name: str,
    step_idx: int = 0,
) -> list[int]:
    """Extract and strictly validate 10-ball prize counts summing to 18 for a single draw."""
    if isinstance(actual_item, CanonicalDrawRecord):
        if len(actual_item.prizes_last2) != PRIZES_PER_DRAW:
            raise DataIntegrityError(
                f"CanonicalDrawRecord at step {step_idx} must have {PRIZES_PER_DRAW} prizes, "
                f"got {len(actual_item.prizes_last2)}."
            )
        expected_tens = [0] * CAGE_NUM_BALLS
        expected_units = [0] * CAGE_NUM_BALLS
        for p in actual_item.prizes_last2:
            clean_p = validate_two_digit_ascii(p)
            expected_tens[ord(clean_p[0]) - 48] += 1
            expected_units[ord(clean_p[1]) - 48] += 1
        if (
            list(actual_item.tens_counts) != expected_tens
            or list(actual_item.units_counts) != expected_units
        ):
            raise DataIntegrityError(
                f"CanonicalDrawRecord at step {step_idx} has counts inconsistent with prizes_last2."
            )
        raw_counts: Sequence[Any] = (
            actual_item.tens_counts if cage_name == "tens_cage" else actual_item.units_counts
        )
    elif isinstance(actual_item, np.ndarray):
        if actual_item.dtype == np.bool_ or actual_item.shape != (CAGE_NUM_BALLS,):
            raise DataIntegrityError(
                f"Invalid actual_counts ndarray at step {step_idx}: "
                f"shape={actual_item.shape}, dtype={actual_item.dtype}."
            )
        raw_counts = actual_item.tolist()
    elif isinstance(actual_item, Sequence) and not isinstance(actual_item, (str, bytes)):
        raw_counts = actual_item
    else:
        raise DataIntegrityError(
            f"Invalid actual_counts item at step {step_idx}: {type(actual_item).__name__}."
        )

    counts: list[int] = []
    for c in raw_counts:
        if isinstance(c, bool) or not isinstance(c, (int, np.integer)):
            raise DataIntegrityError(
                f"Count element at step {step_idx} must be strict int "
                f"(not bool/float/str), got {c!r}."
            )
        counts.append(int(c))

    if len(counts) != CAGE_NUM_BALLS or sum(counts) != PRIZES_PER_DRAW:
        raise DataIntegrityError(
            f"actual_counts at step {step_idx} must have 10 elements summing to 18."
        )
    if any(c < 0 or c > PRIZES_PER_DRAW for c in counts):
        raise DataIntegrityError(f"Negative or out-of-range count at step {step_idx}.")
    return counts


def compute_rank_ordered_alpha_decay(
    ranked_balls_Or_predictions: Sequence[Sequence[int] | CalibratedCagePrediction],
    actual_counts_or_draws: Sequence[Sequence[int] | CanonicalDrawRecord],
    *,
    cage_name: str = "tens_cage",
) -> list[float]:
    """Compute empirical out-of-sample hit frequency by predicted rank (Rank 1 .. Rank 10).

    Guarantees sum_{r=1}^{10} f_{Rank r} == 1.0 +/- 1e-9 across all evaluated draws.
    """
    if (
        not isinstance(ranked_balls_Or_predictions, Sequence)
        or isinstance(ranked_balls_Or_predictions, (str, bytes))
        or not isinstance(actual_counts_or_draws, Sequence)
        or isinstance(actual_counts_or_draws, (str, bytes))
        or len(ranked_balls_Or_predictions) == 0
        or len(ranked_balls_Or_predictions) != len(actual_counts_or_draws)
    ):
        raise DataIntegrityError(
            "ranked_balls_Or_predictions and actual_counts_or_draws must be non-empty sequences "
            "of identical length."
        )
    if cage_name not in ("tens_cage", "units_cage"):
        raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")

    rank_hit_totals = np.zeros(CAGE_NUM_BALLS, dtype=np.int64)
    n_eval = len(ranked_balls_Or_predictions)

    for step_idx, (pred_item, actual_item) in enumerate(
        zip(ranked_balls_Or_predictions, actual_counts_or_draws, strict=True)
    ):
        ranks = _extract_ranked_balls_from_pred(pred_item, step_idx=step_idx)
        counts = _extract_counts_from_actual(actual_item, cage_name=cage_name, step_idx=step_idx)

        for rank_pos, ball_digit in enumerate(ranks):
            rank_hit_totals[rank_pos] += int(counts[ball_digit])

    total_prizes = float(n_eval * PRIZES_PER_DRAW)
    freqs = (rank_hit_totals.astype(np.float64) / total_prizes).tolist()
    return validate_probability_simplex(freqs, expected_len=CAGE_NUM_BALLS)
