"""
Explains a ruleset's scoring_config to clinicians: where each measure starts to
count against a patient, and a one-line summary of each rule. Presentation
only; nothing here scores a check-in.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.scoring_config import DIRECTIONS

Band = Sequence[float]  # [low, high, score]; high is exclusive
OPEN_ENDED = 99  # bands use a large sentinel instead of infinity

DIRECTION_LABELS = {"higher_is_worse": "Higher is worse", "higher_is_better": "Higher is better"}

def _fmt(value: float) -> str:
    return f"{value:g}"

def band_score(bands: Sequence[Band], value: float) -> Optional[int]:
    """
    The points a reading earns, or None when no band covers it.

    None rather than 0 is deliberate. A value outside every band has not been
    assessed, and scoring it 0 would report the worst reading a patient can give
    as normal. A top band written [9,10,3] on a 0-10 pain scale cannot match 10,
    which is why every rule's last band carries a sentinel upper bound.
    """
    for low, high, score in bands:
        if low <= value < high:
            return int(score)
    return None

def band_threshold(bands: Sequence[Band], direction: Optional[str] = None) -> Optional[Tuple[float, str]]:
    """
    The value at which a measure starts to score, and which side is worrying.
    The rule's direction decides which end to read: where higher is worse
    (temperature, pain) the threshold is where the quiet band ends, where higher
    is better (oxygen) it is where the quiet band begins. Rules written before
    direction was recorded fall back to reading it off the bands: one that is
    quiet at the low end worries above.
    """
    if not any(b[2] > 0 for b in bands):
        return None
    worse_when_high = direction == "higher_is_worse" if direction in DIRECTIONS else bands[0][2] == 0
    quiet = [b for b in bands if b[2] == 0]
    if worse_when_high:
        return float(quiet[-1][1] if quiet else bands[0][0]), "above"
    return float(quiet[0][0] if quiet else bands[-1][1]), "below"

def bands_for_day(bands_by_day: Dict[str, Sequence[Band]], day: int) -> Optional[Sequence[Band]]:
    for span, bands in bands_by_day.items():
        start, _, end = span.partition("-")
        if int(start) <= day <= int(end):
            return bands
    return None

def personal_best_detector(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    The drop-from-personal-best detector, wherever the rule declares it: as a
    trend signal, or as the whole rule in the older shape.
    """
    if config.get("detector") == "drop_from_personal_best":
        return config
    return next(
        (trend for trend in config.get("trends") or [] if trend.get("detector") == "drop_from_personal_best"),
        None,
    )

def daily_thresholds(
    config: Dict[str, Any],
    days: Sequence[int],
    values: Sequence[Optional[float]],
    score_from: int,
    score_to: int,
) -> Tuple[List[Optional[float]], Optional[str]]:
    """Threshold for each day (None outside the scoring window), plus its direction."""
    thresholds: List[Optional[float]] = []
    direction: Optional[str] = None
    personal_best: Optional[float] = None

    detector = personal_best_detector(config)

    for day, value in zip(days, values):
        threshold: Optional[float] = None
        if detector is not None:
            if personal_best is not None:
                threshold = personal_best * float(detector.get("drop_fraction", 0.5))
            direction = "below"
        else:
            bands = config.get("bands")
            if "bands_by_day" in config:
                bands = bands_for_day(config["bands_by_day"], day)
            found = band_threshold(bands, config.get("direction")) if bands else None
            if found:
                threshold, direction = found

        thresholds.append(threshold if score_from <= day <= score_to else None)
        if value is not None:
            personal_best = value if personal_best is None else max(personal_best, value)

    return thresholds, direction

def _describe_bands(bands: Sequence[Band]) -> str:
    parts = []
    for low, high, score in bands:
        if score <= 0:
            continue
        if high >= OPEN_ENDED:
            span = f"≥{_fmt(low)}"
        elif low == 0:
            span = f"<{_fmt(high)}"
        else:
            span = f"{_fmt(low)}–{_fmt(high)}"
        parts.append(f"{span} → {score:g}")
    return ", ".join(parts) or "never scores"

TREND_WORDING = {
    "delta_vs_rolling_mean": "a jump above this patient's own recent average",
    "reemergence": "settling and then coming back",
    "monotonic_rise": "a steady climb across the window",
    "drop_from_personal_best": "a fall below this patient's own best",
    "streak": "several days abnormal in a row",
}

def describe_trends(config: Dict[str, Any]) -> List[str]:
    """The derived signals a rule watches for, named as they appear in a nurse's reasons."""
    return [
        f"{trend.get('name', trend['detector'])} ({TREND_WORDING.get(trend['detector'], trend['detector'])})"
        for trend in config.get("trends") or []
    ]

def describe_scoring(config: Dict[str, Any]) -> str:
    """One line a clinician can read, e.g. '37.5–38 → 1, 38–38.5 → 2, ≥38.5 → 3'."""
    watched = describe_trends(config)
    if not watched:
        return _describe_threshold(config)
    following = "Also watches " + ", ".join(watched)
    threshold = _describe_threshold(config)
    return following if threshold == NO_RULE else f"{threshold}. {following}"

NO_RULE = "No scoring rule"

def _describe_threshold(config: Dict[str, Any]) -> str:
    if config.get("emergency"):
        return "Yes is an emergency: bypasses scoring and alerts immediately"
    if "binary_score" in config:
        return f"Yes scores {config['binary_score']:g}"
    if config.get("detector") == "drop_from_personal_best":
        pct = round(float(config.get("drop_fraction", 0.5)) * 100)
        return f"Scores {config.get('score', 0):g} when below {pct}% of the patient's personal best"
    if "milestone" in config:
        stages = ", ".join(f"{label} by day {day}" for day, label in config["milestone"].items())
        return f"Expected: {stages}; scores {config.get('score', 0):g} when behind"
    if "bands_by_day" in config:
        return "; ".join(
            f"Days {span.replace('-', '–')}: {_describe_bands(bands)}"
            for span, bands in config["bands_by_day"].items()
        )
    if "bands" in config:
        prefix = "Rise above discharge baseline: " if config.get("relative_to_baseline") else ""
        return prefix + _describe_bands(config["bands"])
    return NO_RULE
