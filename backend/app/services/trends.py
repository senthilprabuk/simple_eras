"""
Trend detectors: the signals read from the patient's own history rather than
from today's answers.

Each detector asks one question of the window and answers with a band score of
0-3, or None when it has nothing to say. None is not zero. Zero means "assessed
and normal", which is a lie while a detector is still warming up, and it would
hide a real problem in the first days after surgery, when the patient has the
least history and the most risk.

Which way a reading has to move to be getting worse is the rule's direction, so
one detector reads a rising temperature and a falling oxygen saturation without
either needing a code path of its own. That is what `Series.worsening` is for:
every detector below reasons about how far a reading has moved the wrong way,
never about whether it went up.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.services.scoring import band_score

HIGHER_IS_WORSE = "higher_is_worse"


def worsening(direction: Optional[str], value: float, reference: float) -> float:
    """
    How far `value` has moved the wrong way from `reference`; negative means it improved.

    The one place a rule's direction turns into arithmetic. Everything that reads
    a change — a delta from the discharge baseline, a gap from a rolling average,
    a steady climb — goes through here, so a fever and a falling oxygen level are
    the same calculation with one word changed.
    """
    return value - reference if direction == HIGHER_IS_WORSE else reference - value


@dataclass(frozen=True)
class Series:
    """One parameter's readings and threshold scores, indexed by post-operative day."""

    direction: str
    values: Dict[int, float]
    scores: Dict[int, int]

    def worsening(self, value: float, reference: float) -> float:
        return worsening(self.direction, value, reference)

    def present(self, first: int, last: int) -> List[Tuple[int, float]]:
        """The days in this span that were actually answered, oldest first. Gaps are simply absent."""
        return [(day, self.values[day]) for day in sorted(self.values) if first <= day <= last]


def delta_vs_rolling_mean(series: Series, day: int, config: Mapping[str, Any]) -> Optional[int]:
    """
    Is today's reading worse than this patient's own recent average, and by how much?

    Scored on the gap rather than the reading, so a patient whose pain sits at 6
    every day raises nothing while one who jumps from 3 to 6 does.
    """
    today = series.values.get(day)
    if today is None:
        return None
    span = int(config.get("window_days", 3))
    recent = [value for _, value in series.present(day - span, day - 1)]
    if not recent or len(recent) < int(config.get("min_observations", span)):
        return None
    # A reading that has improved leaves the delta below every band, so nothing fires.
    return band_score(config["bands"], series.worsening(today, sum(recent) / len(recent)))


def reemergence(series: Series, day: int, config: Mapping[str, Any]) -> Optional[int]:
    """
    Did this settle for a few days and then come back?

    The highest-yield detector in the set: a temperature that settles for two
    days and climbs again on day six is a far stronger infection signal than the
    same reading on day one, and no absolute threshold separates the two.
    """
    if not series.scores.get(day):
        return None
    quiet_needed = int(config.get("normal_days_required", 2))
    quiet = 0
    for earlier in sorted((d for d in series.scores if d < day), reverse=True):
        if series.scores[earlier]:
            # Found the earlier abnormal spell. It only counts as a return if
            # enough normal days separate it from today.
            return int(config["score"]) if quiet >= quiet_needed else None
        quiet += 1
    return None  # Never abnormal before, so this is a first onset, not a return.


def monotonic_rise(series: Series, day: int, config: Mapping[str, Any]) -> Optional[int]:
    """
    Has it crept steadily the wrong way across the window, without ever crossing
    a hard threshold? Catches the slow burn that band scoring alone never sees.
    """
    span = int(config.get("window_days", 5))
    seen = series.present(day - span, day)
    if len(seen) < int(config.get("min_observations", 3)) or seen[-1][0] != day:
        return None
    steps = [series.worsening(later, earlier) for (_, earlier), (_, later) in zip(seen, seen[1:])]
    if any(step < 0 for step in steps):
        return None  # It turned back at some point, so it is not a steady climb.
    if sum(steps) < float(config["min_total_rise"]):
        return None
    return int(config["score"])


def drop_from_personal_best(series: Series, day: int, config: Mapping[str, Any]) -> Optional[int]:
    """
    Has it fallen below a fraction of the best this patient has managed?

    Compared against the patient's own best rather than a population figure, so
    it reads the same for someone walking 300 steps a day and someone walking
    3000. The rule's direction is what makes "best" mean the highest reading;
    the config validator only allows this detector on higher_is_better measures.
    """
    today = series.values.get(day)
    earlier = [value for d, value in series.values.items() if d < day]
    if today is None or not earlier:
        return None
    best = max(earlier)
    if best <= 0 or today >= best * float(config.get("drop_fraction", 0.5)):
        return None
    return int(config["score"])


def streak(abnormal_by_day: Mapping[int, bool], day: int, config: Mapping[str, Any]) -> Optional[int]:
    """
    Has anything at all been abnormal for several days running?

    Spans every measure rather than one, so a patient who is never quite bad
    enough on any single day still surfaces. The run is counted over calendar
    days and a skipped day breaks it: a day with no submission is unknown, and
    unknown is not evidence that the run continued.
    """
    needed = int(config.get("min_days", 3))
    if any(not abnormal_by_day.get(day - back) for back in range(needed)):
        return None
    return int(config["score"])


#: Detectors that read one parameter's own series. `streak` is absent by design:
#: it reads every measure at once and is configured on the ruleset, not a measure.
DETECTORS = {
    "delta_vs_rolling_mean": delta_vs_rolling_mean,
    "reemergence": reemergence,
    "monotonic_rise": monotonic_rise,
    "drop_from_personal_best": drop_from_personal_best,
}

COMPOSITE_DETECTORS = {"streak": streak}


def detect(series: Series, day: int, config: Mapping[str, Any]) -> Optional[int]:
    """Run one parameter-scoped detector. Unknown names are refused by the config validator."""
    return DETECTORS[config["detector"]](series, day, config)


def detector_names() -> Sequence[str]:
    return sorted([*DETECTORS, *COMPOSITE_DETECTORS])
