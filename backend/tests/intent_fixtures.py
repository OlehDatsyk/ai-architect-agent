"""A realistic DesignIntent for the British family house brief, in the shape Claude returns.

Hand-written to match the schema; the live tests (tests/live) exercise the real model.
"""

import copy
import json
from typing import Any


def room(rid: str, name: str, rtype: str, floor: int, area: float, glazing: str = "standard", side: str = "any") -> dict[str, Any]:
    return {"id": rid, "name": name, "type": rtype, "floor": floor, "target_area": area, "glazing": glazing, "preferred_side": side}


def link(a: str, b: str, kind: str = "door") -> dict[str, str]:
    return {"room_a": a, "room_b": b, "kind": kind}


_BRITISH_HOUSE: dict[str, Any] = {
    "understood": True,
    "project_name": "Contemporary British Family House",
    "summary": "A two-storey detached family house with an integral single garage, kitchen/dining room opening to the garden and three bedrooms upstairs.",
    "building_type": "detached_house",
    "style": "contemporary",
    "floors": 2,
    "floor_height": 2.7,
    "footprint_width": 9.6,
    "footprint_depth": 8.5,
    "entrance_room": "hall",
    "rooms": [
        room("hall", "Entrance Hall", "entrance", 0, 10, side="front"),
        room("living_room", "Living Room", "living_room", 0, 20, "large", "front"),
        room("wc", "WC", "wc", 0, 2, "none"),
        room("kitchen_dining", "Kitchen / Dining", "kitchen_dining", 0, 21, "large", "rear"),
        room("utility", "Utility Room", "utility", 0, 10),
        room("garage", "Garage", "garage", 0, 18, "none", "front"),
        room("landing", "Landing", "landing", 1, 13),
        room("master_bedroom", "Master Bedroom", "bedroom", 1, 20, side="front"),
        room("ensuite", "En-suite", "ensuite", 1, 4.4),
        room("bedroom_2", "Bedroom 2", "bedroom", 1, 9, side="rear"),
        room("bedroom_3", "Bedroom 3", "bedroom", 1, 13, side="rear"),
        room("bathroom", "Family Bathroom", "bathroom", 1, 9),
        room("storage", "Airing Cupboard", "storage", 1, 6, "none"),
    ],
    "connections": [
        link("hall", "living_room"), link("hall", "wc"), link("hall", "kitchen_dining"),
        link("kitchen_dining", "utility"), link("utility", "garage"),
        link("landing", "master_bedroom"), link("master_bedroom", "ensuite"), link("landing", "bedroom_2"),
        link("landing", "bedroom_3"), link("landing", "bathroom"), link("landing", "storage"),
    ],
    "stairs": [{"from_floor": 0, "to_floor": 1, "start_room": "hall", "arrival_room": "landing"}],
    "roof": {"type": "gable", "pitch": 35, "material": "slate"},
    "exterior": {"wall_material": "brick", "accent_material": "white_render", "window_frame_material": "dark_metal"},
    "site": {"driveway": True, "patio": True, "balcony_rooms": []},
    "assumptions": [
        "Assumed the second bathroom is an en-suite to the master bedroom.",
        "Placed the garage at the front with access through the utility room.",
    ],
}


def british_house_intent() -> dict[str, Any]:
    return copy.deepcopy(_BRITISH_HOUSE)


def as_reply_text(intent: dict[str, Any]) -> str:
    return json.dumps(intent)


def _intent(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "understood": True, "summary": "", "floor_height": 2.7, "connections": [], "stairs": [],
        "exterior": {"wall_material": "white_render", "accent_material": None, "window_frame_material": "dark_metal"},
        "site": {"driveway": False, "patio": True, "balcony_rooms": []}, "assumptions": [],
    }
    base.update(fields)
    return base


def scandinavian_intent() -> dict[str, Any]:
    return _intent(
        project_name="Scandinavian Timber House", building_type="detached_house", style="scandinavian",
        floors=2, floor_height=2.8, footprint_width=10.8, footprint_depth=8.4, entrance_room="hall",
        rooms=[
            room("hall", "Entrance Hall", "entrance", 0, 9, side="front"),
            room("open_plan", "Kitchen, Dining and Living", "open_plan_living", 0, 58, "floor_to_ceiling", "rear"),
            room("wc", "WC", "wc", 0, 2.5), room("utility", "Utility", "utility", 0, 6),
            room("landing", "Landing", "landing", 1, 10),
            room("bedroom_1", "Main Bedroom", "bedroom", 1, 16, "large", "rear"),
            room("bedroom_2", "Bedroom 2", "bedroom", 1, 13, "large"), room("bedroom_3", "Bedroom 3", "bedroom", 1, 12, "large"),
            room("bedroom_4", "Bedroom 4", "bedroom", 1, 10, "large"), room("bathroom", "Bathroom", "bathroom", 1, 7),
        ],
        connections=[link("hall", "open_plan", "open"), link("hall", "wc"), link("open_plan", "utility"),
                     link("landing", "bedroom_1"), link("landing", "bedroom_2"), link("landing", "bedroom_3"),
                     link("landing", "bedroom_4"), link("landing", "bathroom")],
        stairs=[{"from_floor": 0, "to_floor": 1, "start_room": "hall", "arrival_room": "landing"}],
        roof={"type": "gable", "pitch": 45, "material": "standing_seam_metal"},
        exterior={"wall_material": "timber_cladding", "accent_material": None, "window_frame_material": "wood"},
    )


def bungalow_intent() -> dict[str, Any]:
    return _intent(
        project_name="Modern Flat-Roof Bungalow", building_type="bungalow", style="modern", floors=1, floor_height=3.0,
        footprint_width=14, footprint_depth=9.5, entrance_room="hall",
        rooms=[
            room("hall", "Entrance Hall", "entrance", 0, 8, side="front"),
            room("open_plan", "Kitchen, Dining and Living", "open_plan_living", 0, 48, "floor_to_ceiling", "rear"),
            room("master_bedroom", "Master Bedroom", "bedroom", 0, 16, side="front"),
            room("ensuite", "En-suite", "ensuite", 0, 4),
            room("bedroom_2", "Bedroom 2", "bedroom", 0, 12, side="front"), room("bedroom_3", "Bedroom 3", "bedroom", 0, 10),
            room("bathroom", "Bathroom", "bathroom", 0, 6), room("utility", "Utility", "utility", 0, 5),
            room("corridor", "Bedroom Corridor", "hallway", 0, 6),
        ],
        connections=[link("hall", "open_plan", "open"), link("hall", "corridor"), link("corridor", "master_bedroom"),
                     link("master_bedroom", "ensuite"), link("corridor", "bedroom_2"), link("corridor", "bedroom_3"),
                     link("corridor", "bathroom"), link("open_plan", "utility")],
        roof={"type": "flat", "pitch": 2, "material": "flat_roofing"},
        site={"driveway": True, "patio": True, "balcony_rooms": []},
    )


def office_intent() -> dict[str, Any]:
    return _intent(
        project_name="Two-Storey Modern Office", building_type="office", style="modern", floors=2, floor_height=3.4,
        footprint_width=16, footprint_depth=11, entrance_room="reception",
        rooms=[
            room("reception", "Reception", "reception", 0, 22, "large", "front"),
            room("workspace", "Open Workspace", "workspace", 0, 70, "large"),
            room("kitchen", "Staff Kitchen", "kitchen", 0, 12), room("toilets_g", "Toilets", "wc", 0, 8),
            room("stair_hall", "Stair Hall", "hallway", 0, 14),
            room("landing", "Landing", "landing", 1, 14),
            room("meeting_1", "Meeting Room 1", "meeting_room", 1, 24, "large"), room("meeting_2", "Meeting Room 2", "meeting_room", 1, 16, "large"),
            room("office_1", "Manager Office 1", "office", 1, 14), room("office_2", "Manager Office 2", "office", 1, 14),
            room("breakout", "Breakout Area", "workspace", 1, 50, "large"), room("toilets_1", "Toilets", "wc", 1, 8),
        ],
        connections=[link("reception", "stair_hall"), link("stair_hall", "workspace"), link("stair_hall", "kitchen"),
                     link("stair_hall", "toilets_g"), link("landing", "meeting_1"), link("landing", "meeting_2"),
                     link("landing", "office_1"), link("landing", "office_2"), link("landing", "breakout"),
                     link("landing", "toilets_1")],
        stairs=[{"from_floor": 0, "to_floor": 1, "start_room": "stair_hall", "arrival_room": "landing"}],
        roof={"type": "flat", "pitch": 2, "material": "flat_roofing"},
        exterior={"wall_material": "concrete", "accent_material": "dark_metal", "window_frame_material": "aluminium"},
        site={"driveway": True, "patio": False, "balcony_rooms": []},
    )


def luxury_intent() -> dict[str, Any]:
    return _intent(
        project_name="Large Contemporary House", building_type="detached_house", style="contemporary", floors=2,
        floor_height=2.9, footprint_width=16, footprint_depth=10.5, entrance_room="hall",
        rooms=[
            room("hall", "Entrance Hall", "entrance", 0, 14, side="front"),
            room("garage", "Double Garage", "garage", 0, 34, "none", "front"),
            room("office", "Home Office", "office", 0, 12, side="front"),
            room("living_room", "Living Room", "living_room", 0, 32, "large", "rear"),
            room("kitchen_dining", "Open-Plan Kitchen and Dining", "kitchen_dining", 0, 40, "floor_to_ceiling", "rear"),
            room("utility", "Utility", "utility", 0, 7), room("wc", "WC", "wc", 0, 3),
            room("landing", "Landing", "landing", 1, 14),
            room("master_bedroom", "Master Bedroom", "bedroom", 1, 24, "large", "rear"),
            room("ensuite", "En-suite", "ensuite", 1, 7), room("dressing", "Dressing Room", "storage", 1, 6),
            room("bedroom_2", "Bedroom 2", "bedroom", 1, 16), room("bedroom_3", "Bedroom 3", "bedroom", 1, 14),
            room("bedroom_4", "Bedroom 4", "bedroom", 1, 13), room("bathroom", "Family Bathroom", "bathroom", 1, 9),
            room("store_1", "Linen Store", "storage", 1, 3),
        ],
        connections=[link("hall", "garage"), link("hall", "office"), link("hall", "living_room"), link("hall", "kitchen_dining", "open"),
                     link("hall", "wc"), link("kitchen_dining", "living_room", "open"), link("kitchen_dining", "utility"),
                     link("landing", "master_bedroom"), link("master_bedroom", "ensuite"), link("master_bedroom", "dressing"),
                     link("landing", "bedroom_2"), link("landing", "bedroom_3"), link("landing", "bedroom_4"),
                     link("landing", "bathroom"), link("landing", "store_1")],
        stairs=[{"from_floor": 0, "to_floor": 1, "start_room": "hall", "arrival_room": "landing"}],
        roof={"type": "hip", "pitch": 25, "material": "slate"},
        exterior={"wall_material": "white_render", "accent_material": "timber_cladding", "window_frame_material": "dark_metal"},
        site={"driveway": True, "patio": True, "balcony_rooms": ["master_bedroom"]},
    )


ALL_INTENTS = {
    "british-family-house": british_house_intent, "scandinavian-house": scandinavian_intent,
    "modern-bungalow": bungalow_intent, "small-office": office_intent, "luxury-house": luxury_intent,
}
