"""SVG floor-plan drawings of a BuildingSpecification, one per floor.

Front of the building is at the bottom, as on a conventional plan. All text comes from the
specification and is XML-escaped, and the frontend shows the SVG as an <img>, so no script
in a room name can run.
"""

from html import escape

from app.geometry.placement import balcony_segment, door_segment, window_segment
from app.geometry.rect import Rect
from app.geometry.stairs import stair_footprint
from app.models.building import BuildingSpecification
from app.models.common import Axis, Side
from app.models.opening import DoorType
from app.models.room import RoomType

SCALE = 48       # pixels per metre
MARGIN = 56
WALL = 4
INK = "#1a1f24"
MUTED = "#59626d"
GLASS = "#4f86b8"
RED = "#b23a2b"

_FILL = {
    RoomType.GARAGE: "#e4e2dc", RoomType.STORAGE: "#ecebe7", RoomType.UTILITY: "#e8ece9",
    RoomType.BATHROOM: "#e3ecef", RoomType.ENSUITE: "#e3ecef", RoomType.WC: "#e3ecef",
    RoomType.ENTRANCE: "#f4f4f1", RoomType.HALLWAY: "#f4f4f1", RoomType.LANDING: "#f4f4f1", RoomType.RECEPTION: "#f4f4f1",
    RoomType.BEDROOM: "#f1ece4",
}
_DEFAULT_FILL = "#eef0ea"


def render_floor(spec: BuildingSpecification, level: int) -> str:
    width, depth = spec.building.width, spec.building.depth
    ox, oy = MARGIN, MARGIN

    def px(x: float) -> float:
        return round(ox + x * SCALE, 1)

    def py(y: float) -> float:
        return round(oy + (depth - y) * SCALE, 1)

    def rect(r: Rect, **attrs: str) -> str:
        extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        return f'<rect x="{px(r.x)}" y="{py(r.y2)}" width="{round(r.width * SCALE, 1)}" height="{round(r.depth * SCALE, 1)}" {extra}/>'

    def line(x1: float, y1: float, x2: float, y2: float, **attrs: str) -> str:
        extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        return f'<line x1="{px(x1)}" y1="{py(y1)}" x2="{px(x2)}" y2="{py(y2)}" {extra}/>'

    parts: list[str] = []
    rooms = spec.rooms_on_floor(level)

    # Balconies sit outside the footprint.
    room_floor = {r.id: r.floor for r in spec.rooms}
    footprint = Rect(0, 0, width, depth)
    for b in spec.balconies:
        if room_floor.get(b.room) != level:
            continue
        seg = balcony_segment(b, footprint)
        r = {
            Side.REAR: Rect(seg.start, depth, b.width, b.depth), Side.FRONT: Rect(seg.start, -b.depth, b.width, b.depth),
            Side.LEFT: Rect(-b.depth, seg.start, b.depth, b.width), Side.RIGHT: Rect(width, seg.start, b.depth, b.width),
        }[b.wall]
        parts.append(rect(r, fill="none", stroke=MUTED, stroke_width="1.5", stroke_dasharray="5 4"))

    for room in rooms:
        r = Rect(room.x, room.y, room.width, room.depth)
        parts.append(rect(r, fill=_FILL.get(room.type, _DEFAULT_FILL), stroke=INK, stroke_width="1.5"))

    # Stairs on this floor, and stairwells arriving from below.
    for stair in spec.stairs:
        r = stair_footprint(stair)
        if stair.from_floor == level:
            parts.append(rect(r, fill="#ffffff", stroke=INK, stroke_width="1"))
            for i in range(1, stair.risers - 1):
                y = r.y + i * stair.run
                parts.append(line(r.x, y, r.x2, y, stroke=INK, stroke_width="0.75"))
            cx = r.x + r.width / 2
            parts.append(line(cx, r.y + 0.15, cx, r.y2 - 0.25, stroke=RED, stroke_width="1.5"))
            parts.append(f'<polygon points="{px(cx - 0.12)},{py(r.y2 - 0.3)} {px(cx + 0.12)},{py(r.y2 - 0.3)} {px(cx)},{py(r.y2 - 0.08)}" fill="{RED}"/>')
        elif stair.to_floor == level:
            parts.append(rect(r, fill="#ffffff", stroke=MUTED, stroke_width="1", stroke_dasharray="4 3"))
            parts.append(line(r.x, r.y, r.x2, r.y2, stroke=MUTED, stroke_width="0.75"))
            parts.append(line(r.x2, r.y, r.x, r.y2, stroke=MUTED, stroke_width="0.75"))

    parts.append(rect(footprint, fill="none", stroke=INK, stroke_width=str(WALL)))

    for window in spec.windows:
        if room_floor.get(window.room) != level:
            continue
        seg = window_segment(window, footprint)
        coords = (seg.start, seg.coord, seg.end, seg.coord) if seg.axis is Axis.X else (seg.coord, seg.start, seg.coord, seg.end)
        parts.append(line(*coords, stroke="#ffffff", stroke_width=str(WALL + 1)))
        parts.append(line(*coords, stroke=GLASS, stroke_width="3"))

    for door in spec.doors:
        if door.floor != level:
            continue
        seg = door_segment(door)
        coords = (seg.start, seg.coord, seg.end, seg.coord) if seg.axis is Axis.X else (seg.coord, seg.start, seg.coord, seg.end)
        gap = WALL + 2 if door.is_external else 4
        parts.append(line(*coords, stroke=_FILL_BEHIND, stroke_width=str(gap)))
        if door.type is not DoorType.OPENING:
            parts.append(line(*coords, stroke=RED if door.is_external else MUTED, stroke_width="1.5", stroke_dasharray="2 2"))

    stair_boxes = [stair_footprint(s) for s in spec.stairs if level in (s.from_floor, s.to_floor)]
    for room in rooms:
        cx, cy = room.x + room.width / 2, _label_y(Rect(room.x, room.y, room.width, room.depth), stair_boxes)
        size = max(9, min(13, room.width * SCALE / max(len(room.name), 1) * 1.7))
        parts.append(f'<text x="{px(cx)}" y="{py(cy) - 2}" font-size="{size:.0f}" text-anchor="middle" fill="{INK}" font-weight="600">{escape(room.name)}</text>')
        parts.append(f'<text x="{px(cx)}" y="{py(cy) + size}" font-size="{max(size - 2, 8):.0f}" text-anchor="middle" fill="{MUTED}">{room.area:.1f} m²</text>')

    floor = spec.floor(level)
    title = escape(floor.name if floor else f"Floor {level}")
    w, h = width * SCALE + 2 * MARGIN, depth * SCALE + 2 * MARGIN
    parts.append(f'<text x="{w / 2}" y="{h - 18}" font-size="12" text-anchor="middle" fill="{MUTED}">Front · {width:g} m</text>')
    parts.append(f'<text x="{MARGIN}" y="26" font-size="15" fill="{INK}" font-weight="600">{title}</text>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" '
        f'font-family="Archivo, Helvetica, Arial, sans-serif" role="img" aria-label="{title} plan">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>' + "".join(parts) + "</svg>"
    )


_FILL_BEHIND = "#ffffff"


def _label_y(room: Rect, obstacles: list[Rect]) -> float:
    """Vertical label position: the room's centre, or the middle of its largest band clear of stairs."""
    blocking = [o for o in obstacles if room.intersection_area(o) > 0]
    if not blocking:
        return room.y + room.depth / 2
    edges = sorted([room.y, room.y2] + [v for o in blocking for v in (max(o.y, room.y), min(o.y2, room.y2))])
    bands = [(a, b) for a, b in zip(edges, edges[1:]) if not any(o.y < (a + b) / 2 < o.y2 for o in blocking)]
    a, b = max(bands, key=lambda band: band[1] - band[0], default=(room.y, room.y2))
    return (a + b) / 2


def render_all(spec: BuildingSpecification) -> list[tuple[int, str, str]]:
    """(level, floor name, svg) for every floor."""
    return [(f.level, f.name, render_floor(spec, f.level)) for f in sorted(spec.floors, key=lambda f: f.level)]
