"""Builds the example BuildingSpecifications in examples/specifications/.

The layouts are hand-designed. Small helpers derive door positions from the wall two rooms
share, which keeps the coordinates consistent; the validator then checks every file
independently (see tests/test_examples.py).

Run from backend/:   python -m scripts.build_example_specs
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.geometry.rect import Rect, shared_segment
from app.geometry.stairs import calculate_stair
from app.models import (
    ArchitecturalStyle,
    Axis,
    Balcony,
    BuildingInfo,
    BuildingSpecification,
    BuildingType,
    Door,
    DoorType,
    Environment,
    Exterior,
    Floor,
    MaterialId,
    MaterialRef,
    Point2D,
    ProjectInfo,
    Roof,
    RoofType,
    Room,
    RoomType,
    Side,
    SiteArea,
    Stair,
    StairDirection,
    Sun,
    Vegetation,
    VegetationKind,
    Window,
    WindowStyle,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
CREATED_AT = datetime(2026, 10, 2, tzinfo=UTC)


class Layout:
    """Collects rooms and openings for one building and derives positions from geometry."""

    def __init__(self, width: float, depth: float) -> None:
        self.width, self.depth = width, depth
        self.rooms: dict[str, Room] = {}
        self.doors: list[Door] = []
        self.windows: list[Window] = []

    def room(self, rid: str, name: str, rtype: RoomType, floor: int, x0: float, y0: float, x1: float, y1: float) -> None:
        self.rooms[rid] = Room(id=rid, name=name, type=rtype, floor=floor, x=x0, y=y0,
                               width=round(x1 - x0, 4), depth=round(y1 - y0, 4))

    def _rect(self, rid: str) -> Rect:
        r = self.rooms[rid]
        return Rect(r.x, r.y, r.width, r.depth)

    def door(self, did: str, a: str, b: str, *, at: float | None = None, width: float = 0.9,
             dtype: DoorType = DoorType.INTERNAL, height: float = 2.1) -> None:
        """Internal door on the wall shared by rooms a and b, centred at `at` along that wall."""
        wall = shared_segment(self._rect(a), self._rect(b))
        if wall is None:
            raise ValueError(f"{a} and {b} do not share a wall")
        centre = (wall.start + wall.end) / 2 if at is None else at
        position = Point2D(x=centre, y=wall.coord) if wall.axis is Axis.X else Point2D(x=wall.coord, y=centre)
        self.doors.append(Door(
            id=did, type=dtype, floor=self.rooms[a].floor, position=position,
            rotation=0 if wall.axis is Axis.X else 90, width=width, height=height,
            connects_room_a=a, connects_room_b=b, is_external=False,
        ))

    def external_door(self, did: str, room: str, side: Side, offset: float, *, width: float = 1.0,
                      dtype: DoorType = DoorType.FRONT, height: float = 2.1) -> None:
        positions = {
            Side.FRONT: (Point2D(x=offset, y=0), 0), Side.REAR: (Point2D(x=offset, y=self.depth), 180),
            Side.LEFT: (Point2D(x=0, y=offset), 90), Side.RIGHT: (Point2D(x=self.width, y=offset), 270),
        }
        position, rotation = positions[side]
        self.doors.append(Door(
            id=did, type=dtype, floor=self.rooms[room].floor, position=position, rotation=rotation,
            width=width, height=height, connects_room_a=room, is_external=True,
        ))

    def window(self, wid: str, room: str, side: Side, offset: float, width: float, height: float = 1.3,
               sill: float = 0.9, style: WindowStyle = WindowStyle.CASEMENT) -> None:
        self.windows.append(Window(id=wid, style=style, room=room, wall=side, offset=offset,
                                   width=width, height=height, sill_height=sill))


def floors(*heights: float, names: tuple[str, ...] = ("Ground floor", "First floor")) -> list[Floor]:
    result, elevation = [], 0.0
    for level, height in enumerate(heights):
        result.append(Floor(level=level, name=names[level], elevation=round(elevation, 4), height=height))
        elevation += height
    return result


def stair(sid: str, x: float, y_start: float, width: float, floor_to_floor: float, *, run: float = 0.25,
          direction: StairDirection = StairDirection.FRONT_TO_REAR) -> Stair:
    dims = calculate_stair(floor_to_floor, run=run)
    y = y_start if direction is StairDirection.FRONT_TO_REAR else round(y_start - dims.going_length, 4)
    return Stair(id=sid, from_floor=0, to_floor=1, x=x, y=y, width=width, direction=direction,
                 risers=dims.risers, rise=round(dims.rise, 5), run=run)


def spec(slug: str, name: str, description: str, style: ArchitecturalStyle, btype: BuildingType,
         layout: Layout, floor_list: list[Floor], roof: Roof, exterior: Exterior, environment: Environment,
         stairs: list[Stair] = (), balconies: list[Balcony] = ()) -> BuildingSpecification:
    return BuildingSpecification(
        project=ProjectInfo(id=f"example-{slug}", name=name, description=description, style=style, created_at=CREATED_AT),
        building=BuildingInfo(building_type=btype, width=layout.width, depth=layout.depth, floors=len(floor_list),
                              floor_height=floor_list[0].height),
        floors=floor_list, rooms=list(layout.rooms.values()), doors=layout.doors, windows=layout.windows,
        stairs=list(stairs), balconies=list(balconies), roof=roof, exterior=exterior, environment=environment,
    )


def m(material_id: MaterialId, colour: str | None = None) -> MaterialRef:
    return MaterialRef(id=material_id, colour=colour)


# --------------------------------------------------------------------------- Example 1
def british_family_house() -> BuildingSpecification:
    L = Layout(9.6, 8.5)
    R = RoomType
    # Ground floor
    L.room("garage", "Garage", R.GARAGE, 0, 0, 0, 3.0, 6.0)
    L.room("hall", "Entrance Hall", R.ENTRANCE, 0, 3.0, 0, 5.2, 4.6)
    L.room("living_room", "Living Room", R.LIVING_ROOM, 0, 5.2, 0, 9.6, 4.6)
    L.room("wc", "WC", R.WC, 0, 3.0, 4.6, 4.2, 6.0)
    L.room("kitchen_dining", "Kitchen / Dining", R.KITCHEN_DINING, 0, 4.2, 4.6, 9.6, 8.5)
    L.room("utility", "Utility Room", R.UTILITY, 0, 0, 6.0, 4.2, 8.5)
    # First floor
    L.room("storage_f1", "Airing Cupboard", R.STORAGE, 1, 0, 0, 3.0, 2.4)
    L.room("bathroom", "Family Bathroom", R.BATHROOM, 1, 0, 2.4, 3.0, 6.0)
    L.room("landing", "Landing", R.LANDING, 1, 3.0, 0, 5.2, 6.0)
    L.room("master_bedroom", "Master Bedroom", R.BEDROOM, 1, 5.2, 0, 9.6, 4.6)
    L.room("ensuite", "En-suite", R.ENSUITE, 1, 7.4, 4.6, 9.6, 6.6)
    L.room("bedroom_2", "Bedroom 2", R.BEDROOM, 1, 5.2, 4.6, 7.4, 8.5)
    L.room("wardrobe", "Walk-in Wardrobe", R.STORAGE, 1, 7.4, 6.6, 9.6, 8.5)
    L.room("bedroom_3", "Bedroom 3", R.BEDROOM, 1, 0, 6.0, 5.2, 8.5)

    L.external_door("door_front", "hall", Side.FRONT, 4.5, width=1.0)
    L.external_door("door_garage", "garage", Side.FRONT, 1.5, width=2.4, height=2.1, dtype=DoorType.GARAGE)
    L.external_door("door_patio", "kitchen_dining", Side.REAR, 8.1, width=2.4, dtype=DoorType.PATIO_SLIDING)
    L.external_door("door_utility_rear", "utility", Side.REAR, 1.2, width=0.9, dtype=DoorType.REAR)
    L.door("door_hall_living", "hall", "living_room")
    L.door("door_hall_kitchen", "hall", "kitchen_dining", width=0.85)
    L.door("door_hall_wc", "hall", "wc", width=0.75)
    L.door("door_kitchen_utility", "kitchen_dining", "utility")
    L.door("door_utility_garage", "utility", "garage", at=1.5)
    L.door("door_landing_storage", "landing", "storage_f1", at=0.5, width=0.7)
    L.door("door_landing_bathroom", "landing", "bathroom", at=5.2, width=0.8)
    L.door("door_landing_master", "landing", "master_bedroom")
    L.door("door_master_ensuite", "master_bedroom", "ensuite", width=0.75)
    L.door("door_landing_bedroom_2", "landing", "bedroom_2", width=0.8)
    L.door("door_bedroom_2_wardrobe", "bedroom_2", "wardrobe", width=0.7)
    L.door("door_landing_bedroom_3", "landing", "bedroom_3", at=4.1)

    L.window("win_hall_side", "hall", Side.FRONT, 3.4, 0.6, style=WindowStyle.FIXED)
    L.window("win_living_front", "living_room", Side.FRONT, 7.4, 2.4, height=1.4, sill=0.6)
    L.window("win_living_side", "living_room", Side.RIGHT, 2.3, 1.2)
    L.window("win_kitchen_rear", "kitchen_dining", Side.REAR, 5.4, 1.2, height=1.1, sill=1.0)
    L.window("win_kitchen_side", "kitchen_dining", Side.RIGHT, 6.5, 1.2)
    L.window("win_utility_rear", "utility", Side.REAR, 3.0, 0.9, height=1.0, sill=1.1)
    L.window("win_utility_side", "utility", Side.LEFT, 7.25, 0.9, height=1.0, sill=1.1)
    L.window("win_landing_front", "landing", Side.FRONT, 4.3, 1.0)
    L.window("win_bathroom", "bathroom", Side.LEFT, 4.2, 0.8, height=0.9, sill=1.2)
    L.window("win_master_front", "master_bedroom", Side.FRONT, 7.4, 1.8)
    L.window("win_master_side", "master_bedroom", Side.RIGHT, 2.3, 1.2)
    L.window("win_ensuite", "ensuite", Side.RIGHT, 5.6, 0.6, height=0.8, sill=1.3)
    L.window("win_bedroom_2", "bedroom_2", Side.REAR, 6.3, 1.2)
    L.window("win_bedroom_3_rear", "bedroom_3", Side.REAR, 2.6, 1.6)
    L.window("win_bedroom_3_side", "bedroom_3", Side.LEFT, 7.25, 1.0)

    return spec(
        "british-family-house", "Contemporary British Family House",
        "Two-storey detached house: three bedrooms, family bathroom and en-suite, kitchen/dining, separate living room, WC, utility and integral single garage.",
        ArchitecturalStyle.CONTEMPORARY, BuildingType.DETACHED_HOUSE, L, floors(2.7, 2.6),
        Roof(type=RoofType.GABLE, pitch=35, overhang=0.3, material=m(MaterialId.SLATE), ridge_direction=Axis.X),
        Exterior(wall_material=m(MaterialId.BRICK, "#8c4a36"), accent_material=m(MaterialId.WHITE_RENDER),
                 trim_material=m(MaterialId.DARK_METAL), window_frame_material=m(MaterialId.DARK_METAL)),
        Environment(
            driveway=SiteArea(id="driveway", x=0, y=-6.0, width=3.4, depth=6.0, material=m(MaterialId.PAVING)),
            paths=[SiteArea(id="front_path", x=4.0, y=-6.0, width=1.0, depth=6.0, material=m(MaterialId.PAVING))],
            patio=SiteArea(id="rear_patio", x=4.2, y=8.5, width=5.4, depth=3.0, material=m(MaterialId.PAVING)),
            vegetation=[Vegetation(id="tree_front", kind=VegetationKind.TREE, x=8.0, y=-4.0, size=5),
                        Vegetation(id="hedge_rear", kind=VegetationKind.HEDGE, x=1.5, y=12.0, size=1.5)],
        ),
        stairs=[stair("stair_main", 3.05, 1.1, 0.9, 2.7)],
    )


# --------------------------------------------------------------------------- Example 2
def scandinavian_house() -> BuildingSpecification:
    L = Layout(10.8, 8.4)
    R = RoomType
    L.room("hall", "Entrance Hall", R.ENTRANCE, 0, 0, 0, 2.8, 4.2)
    L.room("wc", "WC", R.WC, 0, 0, 4.2, 2.8, 5.8)
    L.room("utility", "Utility Room", R.UTILITY, 0, 0, 5.8, 2.8, 8.4)
    L.room("open_plan", "Kitchen, Dining and Living", R.OPEN_PLAN_LIVING, 0, 2.8, 0, 10.8, 8.4)
    L.room("landing", "Landing", R.LANDING, 1, 0, 0, 2.8, 5.8)
    L.room("bathroom", "Bathroom", R.BATHROOM, 1, 0, 5.8, 2.8, 8.4)
    L.room("bedroom_1", "Main Bedroom", R.BEDROOM, 1, 2.8, 0, 6.8, 4.2)
    L.room("bedroom_2", "Bedroom 2", R.BEDROOM, 1, 6.8, 0, 10.8, 4.2)
    L.room("corridor", "Upper Corridor", R.HALLWAY, 1, 2.8, 4.2, 10.8, 5.4)
    L.room("bedroom_3", "Bedroom 3", R.BEDROOM, 1, 2.8, 5.4, 6.8, 8.4)
    L.room("bedroom_4", "Bedroom 4", R.BEDROOM, 1, 6.8, 5.4, 10.8, 8.4)

    L.external_door("door_front", "hall", Side.FRONT, 1.9)
    L.external_door("door_patio", "open_plan", Side.REAR, 8.6, width=2.4, dtype=DoorType.PATIO_SLIDING)
    L.external_door("door_utility_rear", "utility", Side.REAR, 1.4, width=0.9, dtype=DoorType.REAR)
    L.door("opening_hall_living", "hall", "open_plan", width=2.0, dtype=DoorType.OPENING)
    L.door("door_hall_wc", "hall", "wc", at=2.0, width=0.75)
    L.door("door_utility_living", "utility", "open_plan")
    L.door("door_landing_bathroom", "landing", "bathroom", at=1.4, width=0.8)
    L.door("door_landing_bedroom_1", "landing", "bedroom_1", at=1.5)
    L.door("opening_landing_corridor", "landing", "corridor", width=1.0, dtype=DoorType.OPENING)
    L.door("door_corridor_bedroom_2", "corridor", "bedroom_2")
    L.door("door_corridor_bedroom_3", "corridor", "bedroom_3")
    L.door("door_corridor_bedroom_4", "corridor", "bedroom_4")

    L.window("win_living_front_1", "open_plan", Side.FRONT, 5.0, 2.0, height=1.6, sill=0.6)
    L.window("win_living_front_2", "open_plan", Side.FRONT, 8.8, 2.0, height=1.6, sill=0.6)
    L.window("win_living_rear", "open_plan", Side.REAR, 5.0, 2.4, height=2.3, sill=0, style=WindowStyle.FLOOR_TO_CEILING)
    L.window("win_living_side", "open_plan", Side.RIGHT, 4.2, 1.6, height=1.6, sill=0.6, style=WindowStyle.FIXED)
    L.window("win_wc", "wc", Side.LEFT, 5.0, 0.6, height=0.7, sill=1.4)
    L.window("win_utility", "utility", Side.LEFT, 7.1, 0.8, height=1.0, sill=1.1)
    L.window("win_landing", "landing", Side.FRONT, 1.9, 1.0)
    L.window("win_bathroom_rear", "bathroom", Side.REAR, 1.4, 0.8, height=0.9, sill=1.2)
    L.window("win_bedroom_1", "bedroom_1", Side.FRONT, 4.8, 1.6, height=1.2)
    L.window("win_bedroom_2", "bedroom_2", Side.FRONT, 8.8, 1.6, height=1.2)
    L.window("win_bedroom_2_side", "bedroom_2", Side.RIGHT, 2.1, 1.0, height=1.2)
    L.window("win_bedroom_3", "bedroom_3", Side.REAR, 4.8, 1.6, height=1.2)
    L.window("win_bedroom_4", "bedroom_4", Side.REAR, 8.8, 1.6, height=1.2)

    return spec(
        "scandinavian-house", "Scandinavian Timber House",
        "Minimalist two-storey house in timber cladding with an open-plan ground floor and four bedrooms upstairs.",
        ArchitecturalStyle.SCANDINAVIAN, BuildingType.DETACHED_HOUSE, L, floors(2.8, 2.6),
        Roof(type=RoofType.GABLE, pitch=45, overhang=0.2, material=m(MaterialId.STANDING_SEAM_METAL, "#2b2d2f"), ridge_direction=Axis.X),
        Exterior(wall_material=m(MaterialId.TIMBER_CLADDING, "#3a3632"), trim_material=m(MaterialId.WOOD),
                 window_frame_material=m(MaterialId.WOOD), door_material=m(MaterialId.WOOD)),
        Environment(
            paths=[SiteArea(id="front_path", x=1.4, y=-5.0, width=1.0, depth=5.0, material=m(MaterialId.GRAVEL))],
            patio=SiteArea(id="rear_deck", x=2.8, y=8.4, width=8.0, depth=3.5, material=m(MaterialId.WOOD)),
            vegetation=[Vegetation(id="birch_1", kind=VegetationKind.TREE, x=14.5, y=2.0, size=8),
                        Vegetation(id="birch_2", kind=VegetationKind.TREE, x=15.0, y=7.0, size=7)],
            sky="overcast", sun=Sun(azimuth_deg=200, elevation_deg=25),
        ),
        stairs=[stair("stair_main", 0.2, 0.6, 0.9, 2.8)],  # clear of the 0.3 m exterior wall
    )


# --------------------------------------------------------------------------- Example 3
def modern_bungalow() -> BuildingSpecification:
    L = Layout(13.6, 9.4)
    R = RoomType
    L.room("bedroom_2", "Bedroom 2", R.BEDROOM, 0, 0, 0, 3.6, 4.4)
    L.room("bedroom_3", "Bedroom 3", R.BEDROOM, 0, 3.6, 0, 7.2, 4.4)
    L.room("hall", "Entrance Hall", R.ENTRANCE, 0, 7.2, 0, 9.2, 4.4)
    L.room("master_bedroom", "Master Bedroom", R.BEDROOM, 0, 9.2, 0, 13.6, 5.6)
    L.room("corridor", "Corridor", R.HALLWAY, 0, 0, 4.4, 9.2, 5.6)
    L.room("bathroom", "Bathroom", R.BATHROOM, 0, 0, 5.6, 3.0, 9.4)
    L.room("open_plan", "Kitchen, Dining and Living", R.OPEN_PLAN_LIVING, 0, 3.0, 5.6, 13.6, 9.4)

    L.external_door("door_front", "hall", Side.FRONT, 8.2)
    L.external_door("door_patio", "open_plan", Side.REAR, 8.0, width=2.4, height=2.4, dtype=DoorType.PATIO_SLIDING)
    L.door("opening_hall_corridor", "hall", "corridor", width=1.2, dtype=DoorType.OPENING)
    L.door("door_hall_master", "hall", "master_bedroom")
    L.door("door_corridor_bedroom_2", "corridor", "bedroom_2")
    L.door("door_corridor_bedroom_3", "corridor", "bedroom_3")
    L.door("door_corridor_bathroom", "corridor", "bathroom", width=0.8)
    L.door("opening_corridor_living", "corridor", "open_plan", at=6.2, width=1.6, dtype=DoorType.OPENING)

    L.window("win_bedroom_2_front", "bedroom_2", Side.FRONT, 1.8, 1.4)
    L.window("win_bedroom_2_side", "bedroom_2", Side.LEFT, 2.2, 1.2)
    L.window("win_bedroom_3", "bedroom_3", Side.FRONT, 5.4, 1.6)
    L.window("win_master_front", "master_bedroom", Side.FRONT, 11.4, 2.0)
    L.window("win_master_side", "master_bedroom", Side.RIGHT, 2.8, 1.2)
    L.window("win_bathroom", "bathroom", Side.LEFT, 7.5, 0.8, height=0.8, sill=1.3)
    L.window("win_living_rear_1", "open_plan", Side.REAR, 5.0, 2.4, height=2.4, sill=0, style=WindowStyle.FLOOR_TO_CEILING)
    L.window("win_living_rear_2", "open_plan", Side.REAR, 11.4, 2.4, height=2.4, sill=0, style=WindowStyle.FLOOR_TO_CEILING)
    L.window("win_living_side", "open_plan", Side.RIGHT, 7.5, 1.2, height=1.4, sill=0.9)

    return spec(
        "modern-bungalow", "Modern Flat-Roof Bungalow",
        "Single-storey three-bedroom bungalow with a central open-plan living space and large rear glazing.",
        ArchitecturalStyle.MODERN, BuildingType.BUNGALOW, L, floors(3.0, names=("Ground floor",)),
        Roof(type=RoofType.FLAT, pitch=1.5, overhang=0.4, material=m(MaterialId.FLAT_ROOFING)),
        Exterior(wall_material=m(MaterialId.WHITE_RENDER), accent_material=m(MaterialId.TIMBER_CLADDING),
                 trim_material=m(MaterialId.DARK_METAL), window_frame_material=m(MaterialId.DARK_METAL)),
        Environment(
            driveway=SiteArea(id="driveway", x=9.6, y=-6.0, width=4.0, depth=6.0, material=m(MaterialId.GRAVEL)),
            paths=[SiteArea(id="front_path", x=7.7, y=-6.0, width=1.0, depth=6.0, material=m(MaterialId.PAVING))],
            patio=SiteArea(id="rear_terrace", x=3.0, y=9.4, width=10.6, depth=3.5, material=m(MaterialId.PAVING)),
        ),
    )


# --------------------------------------------------------------------------- Example 4
def small_office() -> BuildingSpecification:
    L = Layout(16.0, 10.0)
    R = RoomType
    L.room("reception", "Reception", R.RECEPTION, 0, 0, 0, 6.0, 5.0)
    L.room("toilets_g", "Toilets", R.WC, 0, 0, 5.0, 3.0, 10.0)
    L.room("kitchen", "Staff Kitchen", R.KITCHEN, 0, 3.0, 5.0, 6.0, 10.0)
    L.room("stair_hall", "Stair Hall", R.HALLWAY, 0, 6.0, 0, 8.4, 10.0)
    L.room("workspace", "Open Workspace", R.WORKSPACE, 0, 8.4, 0, 16.0, 10.0)
    L.room("meeting_1", "Meeting Room 1", R.MEETING_ROOM, 1, 0, 0, 6.0, 4.0)
    L.room("meeting_2", "Meeting Room 2", R.MEETING_ROOM, 1, 0, 4.0, 6.0, 7.0)
    L.room("toilets_f1", "Toilets", R.WC, 1, 0, 7.0, 6.0, 10.0)
    L.room("landing", "Landing", R.LANDING, 1, 6.0, 0, 8.4, 10.0)
    L.room("office_1", "Manager Office 1", R.OFFICE, 1, 8.4, 0, 12.2, 4.0)
    L.room("office_2", "Manager Office 2", R.OFFICE, 1, 12.2, 0, 16.0, 4.0)
    L.room("corridor", "Upper Corridor", R.HALLWAY, 1, 8.4, 4.0, 16.0, 5.6)
    L.room("breakout", "Breakout Workspace", R.WORKSPACE, 1, 8.4, 5.6, 16.0, 10.0)

    L.external_door("door_front", "reception", Side.FRONT, 3.0, width=1.8, height=2.4)
    L.external_door("door_fire_exit", "workspace", Side.REAR, 9.5, width=1.0, dtype=DoorType.REAR)
    L.door("door_reception_stairs", "reception", "stair_hall", at=0.65, width=0.9)
    L.door("door_reception_toilets", "reception", "toilets_g")
    L.door("door_reception_kitchen", "reception", "kitchen")
    L.door("door_stairs_workspace", "stair_hall", "workspace", at=2.5, width=1.2)
    L.door("door_landing_meeting_1", "landing", "meeting_1", at=0.65)
    L.door("door_landing_meeting_2", "landing", "meeting_2", at=6.5)
    L.door("door_landing_toilets", "landing", "toilets_f1", at=8.5)
    L.door("door_landing_office_1", "landing", "office_1", at=2.0)
    L.door("opening_landing_corridor", "landing", "corridor", width=1.2, dtype=DoorType.OPENING)
    L.door("door_corridor_office_2", "corridor", "office_2")
    L.door("door_corridor_breakout", "corridor", "breakout", width=1.2)

    for i, x in enumerate((1.0, 5.0), 1):
        L.window(f"win_reception_{i}", "reception", Side.FRONT, x, 1.4, height=1.8, style=WindowStyle.FIXED)
    for i, x in enumerate((10.0, 12.2, 14.4), 1):
        L.window(f"win_workspace_front_{i}", "workspace", Side.FRONT, x, 1.8, height=1.8, style=WindowStyle.FIXED)
    for i, y in enumerate((2.5, 7.5), 1):
        L.window(f"win_workspace_side_{i}", "workspace", Side.RIGHT, y, 1.8, height=1.8, style=WindowStyle.FIXED)
    L.window("win_workspace_rear", "workspace", Side.REAR, 12.2, 1.8, height=1.8, style=WindowStyle.FIXED)
    L.window("win_kitchen", "kitchen", Side.REAR, 4.5, 1.4, height=1.2, sill=1.1)
    L.window("win_toilets_g", "toilets_g", Side.LEFT, 7.5, 0.8, height=0.7, sill=1.6)
    L.window("win_meeting_1_front", "meeting_1", Side.FRONT, 3.0, 2.4, height=1.8)
    L.window("win_meeting_1_side", "meeting_1", Side.LEFT, 2.0, 1.8, height=1.8)
    L.window("win_meeting_2", "meeting_2", Side.LEFT, 5.5, 1.8, height=1.8)
    L.window("win_toilets_f1", "toilets_f1", Side.LEFT, 8.5, 0.8, height=0.7, sill=1.6)
    L.window("win_landing", "landing", Side.FRONT, 7.6, 1.2, height=1.8)
    L.window("win_office_1", "office_1", Side.FRONT, 10.3, 1.8, height=1.8)
    L.window("win_office_2_front", "office_2", Side.FRONT, 14.1, 1.8, height=1.8)
    L.window("win_office_2_side", "office_2", Side.RIGHT, 2.0, 1.4, height=1.8)
    for i, x in enumerate((10.5, 13.9), 1):
        L.window(f"win_breakout_rear_{i}", "breakout", Side.REAR, x, 1.8, height=1.8)
    L.window("win_breakout_side", "breakout", Side.RIGHT, 7.8, 1.8, height=1.8)

    return spec(
        "small-office", "Two-Storey Modern Office",
        "Small office with reception, open workspace, staff kitchen and toilets downstairs; meeting rooms, manager offices and breakout space upstairs.",
        ArchitecturalStyle.MODERN, BuildingType.OFFICE, L, floors(3.4, 3.4),
        Roof(type=RoofType.FLAT, pitch=2, overhang=0.2, material=m(MaterialId.FLAT_ROOFING)),
        Exterior(wall_material=m(MaterialId.CONCRETE), accent_material=m(MaterialId.DARK_METAL),
                 trim_material=m(MaterialId.DARK_METAL), window_frame_material=m(MaterialId.ALUMINIUM),
                 door_material=m(MaterialId.GLASS)),
        Environment(
            driveway=SiteArea(id="car_park", x=8.4, y=-12.0, width=7.6, depth=10.0, material=m(MaterialId.CONCRETE)),
            paths=[SiteArea(id="entrance_path", x=2.0, y=-6.0, width=2.0, depth=6.0, material=m(MaterialId.PAVING))],
        ),
        stairs=[stair("stair_main", 6.1, 1.25, 1.1, 3.4, run=0.28)],
    )


# --------------------------------------------------------------------------- Example 5
def luxury_house() -> BuildingSpecification:
    L = Layout(16.0, 10.0)
    R = RoomType
    L.room("garage", "Double Garage", R.GARAGE, 0, 0, 0, 6.0, 5.6)
    L.room("hall", "Entrance Hall", R.ENTRANCE, 0, 6.0, 0, 9.0, 5.6)
    L.room("office", "Home Office", R.OFFICE, 0, 9.0, 0, 12.0, 5.6)
    L.room("living_room", "Living Room", R.LIVING_ROOM, 0, 12.0, 0, 16.0, 10.0)
    L.room("utility", "Utility Room", R.UTILITY, 0, 0, 5.6, 3.0, 10.0)
    L.room("kitchen_dining", "Open-Plan Kitchen and Dining", R.KITCHEN_DINING, 0, 3.0, 5.6, 12.0, 10.0)
    L.room("bedroom_2", "Bedroom 2", R.BEDROOM, 1, 0, 0, 6.0, 4.0)
    L.room("landing", "Landing", R.LANDING, 1, 6.0, 0, 9.0, 5.4)
    L.room("bedroom_4", "Bedroom 4", R.BEDROOM, 1, 9.0, 0, 16.0, 4.0)
    L.room("corridor_west", "West Corridor", R.HALLWAY, 1, 0, 4.0, 6.0, 5.4)
    L.room("corridor_east", "East Corridor", R.HALLWAY, 1, 9.0, 4.0, 16.0, 5.4)
    L.room("bedroom_3", "Bedroom 3", R.BEDROOM, 1, 0, 5.4, 4.6, 10.0)
    L.room("bathroom", "Family Bathroom", R.BATHROOM, 1, 4.6, 5.4, 9.0, 10.0)
    L.room("ensuite", "En-suite", R.ENSUITE, 1, 9.0, 5.4, 11.4, 10.0)
    L.room("master_bedroom", "Master Bedroom", R.BEDROOM, 1, 11.4, 5.4, 16.0, 10.0)

    L.external_door("door_front", "hall", Side.FRONT, 8.0, width=1.0, height=2.3)
    L.external_door("door_garage", "garage", Side.FRONT, 3.0, width=4.8, height=2.2, dtype=DoorType.GARAGE)
    L.external_door("door_kitchen_terrace", "kitchen_dining", Side.REAR, 8.0, width=3.0, dtype=DoorType.PATIO_SLIDING)
    L.external_door("door_living_terrace", "living_room", Side.REAR, 14.0, width=2.4, dtype=DoorType.PATIO_SLIDING)
    L.external_door("door_utility_rear", "utility", Side.REAR, 1.5, width=0.9, dtype=DoorType.REAR)
    L.external_door("door_balcony", "master_bedroom", Side.REAR, 13.7, width=2.0, dtype=DoorType.PATIO_SLIDING)
    L.door("door_hall_office", "hall", "office", at=2.5)
    L.door("opening_hall_kitchen", "hall", "kitchen_dining", at=8.0, width=1.6, dtype=DoorType.OPENING)
    L.door("opening_kitchen_living", "kitchen_dining", "living_room", width=2.4, dtype=DoorType.OPENING)
    L.door("door_utility_kitchen", "utility", "kitchen_dining")
    L.door("door_utility_garage", "utility", "garage")
    L.door("door_corridor_bedroom_2", "corridor_west", "bedroom_2", at=3.0)
    L.door("opening_landing_west", "landing", "corridor_west", at=4.95, width=0.8, dtype=DoorType.OPENING)
    L.door("door_corridor_bedroom_3", "corridor_west", "bedroom_3", at=2.3)
    L.door("door_landing_bathroom", "landing", "bathroom", at=8.0, width=0.8)
    L.door("door_landing_bedroom_4", "landing", "bedroom_4", at=2.0)
    L.door("opening_landing_east", "landing", "corridor_east", width=1.0, dtype=DoorType.OPENING)
    L.door("door_corridor_master", "corridor_east", "master_bedroom")
    L.door("door_master_ensuite", "master_bedroom", "ensuite", width=0.8)

    L.window("win_office", "office", Side.FRONT, 10.5, 1.8, height=1.5)
    L.window("win_living_front", "living_room", Side.FRONT, 14.0, 2.8, height=2.0, sill=0.4)
    L.window("win_living_side_1", "living_room", Side.RIGHT, 2.5, 1.6, height=1.5)
    L.window("win_living_side_2", "living_room", Side.RIGHT, 7.5, 1.6, height=1.5)
    L.window("win_kitchen_rear", "kitchen_dining", Side.REAR, 4.8, 1.4, height=1.1, sill=1.0)
    L.window("win_utility", "utility", Side.LEFT, 7.8, 0.9, height=1.0, sill=1.1)
    L.window("win_bedroom_2_front", "bedroom_2", Side.FRONT, 3.0, 1.8)
    L.window("win_bedroom_2_side", "bedroom_2", Side.LEFT, 2.0, 1.2)
    L.window("win_landing", "landing", Side.FRONT, 8.0, 1.2)
    L.window("win_bedroom_4_1", "bedroom_4", Side.FRONT, 11.0, 1.6)
    L.window("win_bedroom_4_2", "bedroom_4", Side.FRONT, 14.5, 1.6)
    L.window("win_bedroom_4_side", "bedroom_4", Side.RIGHT, 2.0, 1.2)
    L.window("win_bedroom_3_rear", "bedroom_3", Side.REAR, 2.3, 1.6)
    L.window("win_bedroom_3_side", "bedroom_3", Side.LEFT, 7.7, 1.2)
    L.window("win_bathroom", "bathroom", Side.REAR, 6.8, 1.0, height=0.9, sill=1.2)
    L.window("win_ensuite", "ensuite", Side.REAR, 10.2, 0.8, height=0.9, sill=1.2)
    L.window("win_master_side", "master_bedroom", Side.RIGHT, 7.7, 1.6)

    return spec(
        "luxury-house", "Large Contemporary House",
        "Large two-storey house with four bedrooms, double garage, home office, open-plan kitchen, large living room, master balcony and rear terrace.",
        ArchitecturalStyle.CONTEMPORARY, BuildingType.DETACHED_HOUSE, L, floors(2.9, 2.7),
        Roof(type=RoofType.HIP, pitch=25, overhang=0.5, material=m(MaterialId.SLATE), ridge_direction=Axis.X),
        Exterior(wall_material=m(MaterialId.WHITE_RENDER), accent_material=m(MaterialId.TIMBER_CLADDING),
                 trim_material=m(MaterialId.DARK_METAL), window_frame_material=m(MaterialId.DARK_METAL)),
        Environment(
            driveway=SiteArea(id="driveway", x=0, y=-7.0, width=6.0, depth=7.0, material=m(MaterialId.GRAVEL)),
            paths=[SiteArea(id="front_path", x=7.5, y=-7.0, width=1.0, depth=7.0, material=m(MaterialId.PAVING))],
            patio=SiteArea(id="rear_terrace", x=3.0, y=10.0, width=13.0, depth=4.0, material=m(MaterialId.PAVING)),
            vegetation=[Vegetation(id="tree_front", kind=VegetationKind.TREE, x=13.0, y=-4.5, size=6),
                        Vegetation(id="shrubs_front", kind=VegetationKind.SHRUB, x=10.0, y=-2.0, size=1)],
            sun=Sun(azimuth_deg=160, elevation_deg=45),
        ),
        stairs=[stair("stair_main", 6.05, 4.4, 1.0, 2.9, run=0.26, direction=StairDirection.REAR_TO_FRONT)],
        balconies=[Balcony(id="balcony_master", room="master_bedroom", wall=Side.REAR, offset=13.7, width=3.2, depth=1.5)],
    )


EXAMPLES = {
    "british-family-house": (british_family_house, "Create a two-storey contemporary British detached house with three bedrooms, two bathrooms, an open-plan kitchen and dining area, separate living room, downstairs WC, utility room and single garage."),
    "scandinavian-house": (scandinavian_house, "Create a minimalist Scandinavian two-storey house with timber cladding, four bedrooms, large windows and an open-plan ground floor."),
    "modern-bungalow": (modern_bungalow, "Create a modern three-bedroom bungalow with a flat roof, large rear windows and central open-plan living space."),
    "small-office": (small_office, "Create a modern two-storey office containing reception, open workspace, meeting rooms, kitchen, toilets and manager offices."),
    "luxury-house": (luxury_house, "Create a large contemporary house with four bedrooms, double garage, office, open-plan kitchen, large living room, balcony and rear terrace."),
}


def main() -> None:
    for slug, (build, prompt) in EXAMPLES.items():
        specification = build()
        (EXAMPLES_DIR / "specifications" / f"{slug}.json").write_text(
            json.dumps(specification.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
        (EXAMPLES_DIR / "prompts" / f"{slug}.txt").write_text(prompt + "\n", encoding="utf-8")
        print(f"wrote {slug}")


if __name__ == "__main__":
    main()
