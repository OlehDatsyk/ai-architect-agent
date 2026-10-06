"""Pure layout arithmetic: sharing a length between rows, and free intervals on a wall."""

PRECISION = 2  # coordinates are rounded to centimetres


class InfeasibleLayout(ValueError):
    """The rooms cannot be made to fit with their minimum dimensions."""


def distribute(ideal: list[float], minimum: list[float], total: float) -> list[float]:
    """Split `total` between items in proportion to `ideal`, never below `minimum`.

    Items that would fall below their minimum are fixed at it and the rest is shared
    again among the others (water filling).
    """
    if len(ideal) != len(minimum):
        raise ValueError("ideal and minimum must have the same length")
    if not ideal:
        return []
    if sum(minimum) > total + 1e-9:
        raise InfeasibleLayout(f"needs at least {sum(minimum):.2f} m but only {total:.2f} m is available")
    fixed: dict[int, float] = {}
    while True:
        free = [i for i in range(len(ideal)) if i not in fixed]
        remaining = total - sum(fixed.values())
        weight = sum(max(ideal[i], 1e-6) for i in free)
        result = {i: remaining * max(ideal[i], 1e-6) / weight for i in free}
        too_small = [i for i in free if result[i] < minimum[i] - 1e-9]
        if not too_small:
            result.update(fixed)
            return [result[i] for i in range(len(ideal))]
        for i in too_small:
            fixed[i] = minimum[i]


def cut_points(lengths: list[float], start: float, end: float) -> list[float]:
    """Cumulative boundaries from `start` to `end`, rounded so neighbours share exact edges."""
    points = [start]
    running = start
    for length in lengths[:-1]:
        running += length
        points.append(round(running, PRECISION))
    points.append(end)
    return points


def free_intervals(start: float, end: float, occupied: list[tuple[float, float]], margin: float = 0.0) -> list[tuple[float, float]]:
    """Parts of [start, end] not covered by `occupied` (each widened by `margin`)."""
    blocked = sorted((max(start, a - margin), min(end, b + margin)) for a, b in occupied if b + margin > start and a - margin < end)
    free, cursor = [], start
    for a, b in blocked:
        if a > cursor:
            free.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < end:
        free.append((cursor, end))
    return free


def place_in_free_space(start: float, end: float, width: float, occupied: list[tuple[float, float]],
                        margin: float = 0.15, prefer: float | None = None) -> float | None:
    """Centre of an opening of `width` that fits in [start, end] clear of `occupied`,
    as close as possible to `prefer` (default: the middle). None if it cannot fit."""
    target = (start + end) / 2 if prefer is None else prefer
    best: float | None = None
    for a, b in free_intervals(start + margin, end - margin, occupied, margin):
        if b - a + 1e-9 < width:
            continue
        centre = min(max(target, a + width / 2), b - width / 2)
        if best is None or abs(centre - target) < abs(best - target):
            best = centre
    return None if best is None else round(best, PRECISION)
