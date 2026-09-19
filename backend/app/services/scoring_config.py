"""
Checks a parameter's scoring_config before it is saved to a draft ruleset.

The rules engine trusts what it reads: a band written the wrong way round, an
overlapping day range or a misspelt key would silently score nothing, or fail
an evaluation. Here each is refused with a message the author can act on.
"""

from typing import Any, Dict, Iterable, Set, Tuple

# A band scores 0-3. A yes/no answer worth 3 is a critical override on its own.
MAX_POINTS = 3


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


def _check_bands(bands: Any, where: str) -> None:
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
    _only(keys, {"bands", "relative_to_baseline", "bands_by_day", "detector", "drop_fraction", "score"})

    if "detector" in config:
        _only(keys, {"detector", "drop_fraction", "score"})
        if config["detector"] != "drop_from_personal_best":
            raise ScoringConfigError("the only detector is drop_from_personal_best")
        fraction = _number(config.get("drop_fraction"), "drop_fraction")
        if not 0 < fraction < 1:
            raise ScoringConfigError("drop_fraction must be between 0 and 1, e.g. 0.5 for half")
        _points(config.get("score"), "score")
        return

    if "bands_by_day" in config:
        _only(keys, {"bands_by_day"})
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
            _check_bands(bands, f"days {span}")
        return

    if "bands" in config:
        _only(keys, {"bands", "relative_to_baseline"})
        if "relative_to_baseline" in config and not isinstance(config["relative_to_baseline"], bool):
            raise ScoringConfigError("relative_to_baseline must be true or false")
        _check_bands(config["bands"], "bands")
        return

    raise ScoringConfigError("a numeric measure needs bands, bands_by_day or a detector")
