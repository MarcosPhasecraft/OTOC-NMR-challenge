"""
Renders a markdown leaderboard table from the registry and score cache:
one row per registered baseline, one column per instance, ranked by a
chosen metric. Generic as long as metric names and instance ids are
treated as opaque -- nothing here assumes an instance id is a grid side
length or that a metric is called "weight".
"""
from toolkit.cache import ScoreCache, fingerprint
from toolkit.problem import Problem
from toolkit.registry import Registry


class LeaderboardError(Exception):
    """Raised when a leaderboard can't be rendered meaningfully."""


def _cell(value) -> str:
    """
    One table cell, safe to sit between two pipes.

    A label comes from a submitter's own submission.json and is checked
    only for being a non-empty string, so it can contain the one character
    markdown gives structural meaning to. An unescaped "|" splits the row
    and lets a submitter write cells of their own -- forging a column of
    scores in the published table with no code running anywhere. Newlines
    end the row outright. Metric values go through the same path because a
    string metric is legal too.
    """
    text = str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_leaderboard(
    problem: Problem,
    registry: Registry,
    cache: ScoreCache,
    *,
    metric_key: str,
    instances: list = None,
    lower_is_better: bool = True,
) -> str:
    """
    instances: which instance ids to show as columns, in the order
    given. Defaults to the sorted union of every instance any
    registered baseline actually has a cached score for -- sorted with
    Python's plain `<`, so this only gives a meaningful order for
    naturally-ordered ids (ints sort numerically; arbitrary strings
    sort lexicographically, which may not match a problem's own
    intended order for e.g. "8x4"-style ids). Pass an explicit
    `instances` list, in whatever order actually makes sense for your
    problem, to bypass this entirely.

    Ranks rows by the mean of metric_key across whatever instances a
    baseline has a cached score for among `instances` (a missing cell
    is excluded from that mean, not treated as zero); a baseline with
    no cached score for any shown instance sorts last, after every
    baseline that has at least one.

    Raises LeaderboardError rather than rendering a table that would say
    nothing: when no baseline has a cached score under the current
    fingerprint (run a rescore), when no cached score carries metric_key
    (a typo -- the message lists the names that do exist), or when a
    value for it isn't a number. An empty registry is not an error; it
    renders a bare header.
    """
    fp = fingerprint(problem)
    names = registry.names()

    if not names:
        return "| baseline |\n|---|"  # nothing registered yet; not an error

    _check_metric_is_present(registry, cache, fp, names, metric_key)

    if instances is None:
        seen = []
        for name in names:
            for instance_id in registry.get(name)["instances"]:
                if cache.get(fp, name, instance_id) is not None and instance_id not in seen:
                    seen.append(instance_id)
        instances = sorted(seen)
    else:
        # Iterated once per baseline and measured for the separator row,
        # so it has to be a sequence, not something single-pass.
        instances = list(instances)

    rows = []
    for name in names:
        label = registry.get(name)["label"]
        values = {}
        for instance_id in instances:
            score = cache.get(fp, name, instance_id)
            values[instance_id] = score.get(metric_key) if score else None
        present = [v for v in values.values() if v is not None]
        for value in present:
            # A cost metric has to be a number for the mean to mean
            # anything. Say which metric and which value, rather than
            # letting sum() surface "unsupported operand type(s) for +".
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise LeaderboardError(
                    f"baseline {name!r} has a non-numeric value for metric "
                    f"{metric_key!r}: {value!r}. A leaderboard ranks by the mean "
                    "of a metric, so it has to be a number."
                )
        mean = sum(present) / len(present) if present else None
        rows.append((label, values, mean))

    def sort_key(row):
        _, _, mean = row
        if mean is None:
            return (1, 0)
        return (0, mean if lower_is_better else -mean)

    rows.sort(key=sort_key)

    header = "| baseline | " + " | ".join(_cell(i) for i in instances) + " |" if instances else "| baseline |"
    separator = "|---" * (len(instances) + 1) + "|"
    lines = [header, separator]
    for label, values, _ in rows:
        cells = " | ".join("—" if values[i] is None else _cell(values[i]) for i in instances)
        row = f"| {_cell(label)} | {cells} |" if instances else f"| {_cell(label)} |"
        lines.append(row)

    return "\n".join(lines)


def _check_metric_is_present(registry, cache, fp, names, metric_key):
    """
    Distinguishes the two ways a leaderboard comes out empty, because they
    need opposite responses: nothing is cached under the current referee
    (run a rescore), or things are cached but none carries this metric
    (you typed the name wrong). Silently rendering a table of dashes for
    either is how an empty leaderboard gets published.
    """
    available = set()
    any_cached = False
    for name in names:
        for instance_id in registry.get(name)["instances"]:
            score = cache.get(fp, name, instance_id)
            if score is not None:
                any_cached = True
                available.update(score)

    if not any_cached:
        raise LeaderboardError(
            "no registered baseline has a cached score under the current "
            "referee fingerprint, so every cell would be empty. This is the "
            "expected state right after a frozen file changes -- run "
            "toolkit.rescore.rescore() to recompute, then render again."
        )

    if metric_key not in available:
        raise LeaderboardError(
            f"no cached score has a metric named {metric_key!r}. "
            f"Available metrics: {sorted(available)}."
        )
