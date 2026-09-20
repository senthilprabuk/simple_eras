"""
Checks a parameter's scoring_config before it is saved to a draft ruleset.

The rules engine trusts what it reads: a band written the wrong way round, an
overlapping day range or a misspelt key would silently score nothing, or fail
an evaluation. Here each is refused with a message the author can act on.
"""

from typing import Any, Dict, Iterable, Literal, Set, Tuple, get_args

# A band scores 0-3. A yes/no answer worth 3 is a critical override on its own.
MAX_POINTS = 3

# Which way a numeric measure goes wrong: a fever rises, oxygen falls. Every
# numeric rule states it rather than leaving the engine to infer it from where
# the scoring bands sit, which says nothing about readings no band covers.
Direction = Literal["higher_is_worse", "higher_is_better"]
DIRECTIONS: Tuple[str, ...] = get_args(Direction)

MAX_WEIGHT = 10

# Detectors and the settings each one takes, beyond the name, detector and weight
# every trend carries. A detector reading one measure's own history is declared on
# that measure; `streak` spans every measure at once and belongs to the ruleset.
TREND_SETTINGS: Dict[str, Set[str]] = {
    "delta_vs_rolling_mean": {"bands", "window_days", "min_observations"},
    "reemergence": {"score", "normal_days_required"},
    "monotonic_rise": {"score", "window_days", "min_total_rise", "min_observations"},
    "drop_from_personal_best": {"score", "drop_fraction"},
    "streak": {"score", "min_days"},
}
PARAMETER_DETECTORS = {"delta_vs_rolling_mean", "reemergence", "monotonic_rise", "drop_from_personal_best"}
COMPOSITE_DETECTORS = {"streak"}
TREND_COMMON = {"name", "detector", "weight"}


class ScoringConfigError(ValueError):
    pass


def _only(keys: Set[str], allowed: Set[str]) -> None:
    unknown = sorted(keys - allowed)
    if unknown:
        raise ScoringConfigError(
            f"unknown setting {', '.join(unknown)}; allowed here: {', '.join(sorted(allowed))}"
        )


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScoringConfigError(f"{what} must be a number")
    return float(value)


def _points(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_POINTS:
        raise ScoringConfigError(f"{what} must be a whole number from 0 to {MAX_POINTS}")
    return value


def _direction(config: Dict[str, Any]) -> str:
    choices = " or ".join(DIRECTIONS)
    value = config.get("direction")
    if value is None:
        raise ScoringConfigError(f"a numeric measure needs direction: {choices}")
    if value not in DIRECTIONS:
        raise ScoringConfigError(f"direction must be {choices}, not {value!r}")
    return value


def _check_bands(bands: Any, where: str, direction: str) -> None:
    if not isinstance(bands, list) or not bands:
        raise ScoringConfigError(f"{where} must be a list of [from, to, points] bands")
    previous_high = None
    for i, band in enumerate(bands, start=1):
        if not isinstance(band, list) or len(band) != 3:
            raise ScoringConfigError(f"{where}, band {i} must be [from, to, points]")
        low = _number(band[0], f"{where}, band {i} 'from'")
        high = _number(band[1], f"{where}, band {i} 'to'")
        _points(band[2], f"{where}, band {i} points")
        if low >= high:
            raise ScoringConfigError(f"{where}, band {i}: 'from' must be below 'to'")
        if previous_high is not None and low < previous_high:
            raise ScoringConfigError(f"{where}, band {i} overlaps the band before it; list bands from lowest to highest")
        previous_high = high

    # The quiet band sits at the safe end, so it must be opposite the worrying
    # one. Bands where every reading scores say nothing either way, and pass.
    if direction == "higher_is_worse" and bands[0][2] > 0 and bands[-1][2] == 0:
        raise ScoringConfigError(f"{where} score at the low end, so direction is higher_is_better")
    if direction == "higher_is_better" and bands[-1][2] > 0 and bands[0][2] == 0:
        raise ScoringConfigError(f"{where} score at the high end, so direction is higher_is_worse")


def _day(value: Any, observation_days: int, what: str) -> int:
    text = str(value)
    if not text.isdigit() or int(text) > observation_days:
        raise ScoringConfigError(f"{what} must be a day from 0 to {observation_days}")
    return int(text)


def _span(span: str, observation_days: int) -> Tuple[int, int]:
    start, sep, end = span.partition("-")
    if not sep:
        raise ScoringConfigError(f"day range {span!r} must look like '0-3'")
    first = _day(start, observation_days, f"day range {span!r}")
    last = _day(end, observation_days, f"day range {span!r}")
    if first > last:
        raise ScoringConfigError(f"day range {span!r} ends before it starts")
    return first, last


def _whole(value: Any, what: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ScoringConfigError(f"{what} must be a whole number from {low} to {high}")
    return value


def _fraction(value: Any, what: str) -> float:
    fraction = _number(value, what)
    if not 0 < fraction < 1:
        raise ScoringConfigError(f"{what} must be between 0 and 1, e.g. 0.5 for half")
    return fraction


def _check_trend(trend: Any, direction: str, where: str, observation_days: int, allowed_detectors: Set[str]) -> str:
    """Check one trend signal. Returns its name, so a rule cannot declare the same one twice."""
    if not isinstance(trend, dict) or not trend:
        raise ScoringConfigError(f"{where} must be a JSON object")

    detector = trend.get("detector")
    if detector not in allowed_detectors:
        raise ScoringConfigError(
            f"{where}: unknown detector {detector!r}; here you can use {', '.join(sorted(allowed_detectors))}"
        )
    _only(set(trend), TREND_COMMON | TREND_SETTINGS[detector])

    name = trend.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ScoringConfigError(f"{where} needs a name the nurse will see, such as 'pain_rising'")
    _whole(trend.get("weight"), f"{where} weight", 0, MAX_WEIGHT)

    if detector == "delta_vs_rolling_mean":
        # The delta is measured in the worsening direction whichever way the
        # reading moves, so its bands always start quiet at nothing and climb.
        _check_bands(trend.get("bands"), f"{where} bands", "higher_is_worse")
        _whole(trend.get("window_days", 3), f"{where} window_days", 1, observation_days)
        _whole(trend.get("min_observations", 3), f"{where} min_observations", 1, observation_days)
    else:
        _points(trend.get("score"), f"{where} score")

    if detector == "reemergence":
        _whole(trend.get("normal_days_required", 2), f"{where} normal_days_required", 1, observation_days)
    elif detector == "monotonic_rise":
        _whole(trend.get("window_days", 5), f"{where} window_days", 2, observation_days)
        _whole(trend.get("min_observations", 3), f"{where} min_observations", 2, observation_days)
        if _number(trend.get("min_total_rise"), f"{where} min_total_rise") <= 0:
            raise ScoringConfigError(f"{where} min_total_rise must be more than 0")
    elif detector == "drop_from_personal_best":
        if direction != "higher_is_better":
            raise ScoringConfigError(f"{where}: drop_from_personal_best watches for a fall, so direction is higher_is_better")
        _fraction(trend.get("drop_fraction", 0.5), f"{where} drop_fraction")
    elif detector == "streak":
        _whole(trend.get("min_days", 3), f"{where} min_days", 2, observation_days)

    return name


def _check_trends(trends: Any, direction: str, observation_days: int, allowed_detectors: Set[str]) -> None:
    if not isinstance(trends, list) or not trends:
        raise ScoringConfigError("trends must be a list of trend signals")
    seen: Set[str] = set()
    for i, trend in enumerate(trends, start=1):
        name = _check_trend(trend, direction, f"trend {i}", observation_days, allowed_detectors)
        if name in seen:
            raise ScoringConfigError(f"two trends are both called {name!r}; each signal needs its own name")
        seen.add(name)


def validate_composite_config(config: Any, observation_days: int) -> None:
    """
    Check a ruleset's cross-measure signals: the ones that read every measure at
    once rather than belonging to any single one.
    """
    if not isinstance(config, dict):
        raise ScoringConfigError("the ruleset's cross-measure rules must be a JSON object")
    if not config:
        return
    _only(set(config), {"trends"})
    _check_trends(config["trends"], "higher_is_worse", observation_days, COMPOSITE_DETECTORS)


def validate_scoring_config(
    config: Any,
    parameter_type: str,
    option_codes: Iterable[str],
    observation_days: int,
) -> None:
    """Raise ScoringConfigError unless the config is one the rules engine reads correctly."""
    if not isinstance(config, dict) or not config:
        raise ScoringConfigError("the rule must be a JSON object")
    keys = set(config)

    if parameter_type == "boolean":
        _only(keys, {"binary_score", "emergency"})
        if "binary_score" not in config:
            raise ScoringConfigError("a yes/no measure needs binary_score")
        _points(config["binary_score"], "binary_score")
        if "emergency" in config and not isinstance(config["emergency"], bool):
            raise ScoringConfigError("emergency must be true or false")
        return

    if parameter_type == "ordinal":
        _only(keys, {"milestone", "score"})
        milestone = config.get("milestone")
        if not isinstance(milestone, dict) or not milestone:
            raise ScoringConfigError("an ordinal measure needs milestone: {day: option}")
        options = list(option_codes)
        for day, option in milestone.items():
            _day(day, observation_days, f"milestone day {day!r}")
            if option not in options:
                raise ScoringConfigError(f"milestone day {day}: {option!r} is not one of {', '.join(options)}")
        _points(config.get("score"), "score")
        return

    if parameter_type != "numeric":
        raise ScoringConfigError(f"unknown measure type {parameter_type!r}")

    # Name a misspelt key before deciding which kind of rule this is.
    _only(keys, {"direction", "bands", "relative_to_baseline", "bands_by_day",
                 "detector", "drop_fraction", "score", "trends"})
    direction = _direction(config)

    if "trends" in config:
        _check_trends(config["trends"], direction, observation_days, PARAMETER_DETECTORS)

    if "detector" in config:
        # The original shape, where a lone detector is the whole rule. Kept so
        # rulesets approved before trends existed still read; new rules declare
        # their detectors under "trends", where each one carries its own weight.
        _only(keys, {"direction", "detector", "drop_fraction", "score", "trends"})
        if config["detector"] != "drop_from_personal_best":
            raise ScoringConfigError("the only detector that can be a rule on its own is drop_from_personal_best")
        if direction != "higher_is_better":
            raise ScoringConfigError("drop_from_personal_best watches for a fall, so direction is higher_is_better")
        _fraction(config.get("drop_fraction"), "drop_fraction")
        _points(config.get("score"), "score")
        return

    if "bands_by_day" in config:
        _only(keys, {"direction", "bands_by_day", "trends"})
        spans: Dict[str, Any] = config["bands_by_day"]
        if not isinstance(spans, dict) or not spans:
            raise ScoringConfigError("bands_by_day must map day ranges such as '0-3' to bands")
        covered = []
        for span, bands in spans.items():
            first, last = _span(span, observation_days)
            for start, end in covered:
                if first <= end and start <= last:
                    raise ScoringConfigError(f"day ranges {start}-{end} and {span} overlap")
            covered.append((first, last))
            _check_bands(bands, f"days {span}", direction)
        return

    if "bands" in config:
        _only(keys, {"direction", "bands", "relative_to_baseline", "trends"})
        if "relative_to_baseline" in config and not isinstance(config["relative_to_baseline"], bool):
            raise ScoringConfigError("relative_to_baseline must be true or false")
        _check_bands(config["bands"], "bands", direction)
        return

    if "trends" in config:
        return  # A measure watched only for the way it moves, with no band to read today against.

    raise ScoringConfigError("a numeric measure needs bands, bands_by_day, a detector or trends")
