"""Material identifiers. Every material is generated procedurally in Blender (Phase 7)."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import StringConstraints, model_validator

from app.models.common import SpecModel

HexColour = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class MaterialId(StrEnum):
    # Exterior walls
    BRICK = "brick"
    WHITE_RENDER = "white_render"
    CONCRETE = "concrete"
    TIMBER_CLADDING = "timber_cladding"
    DARK_METAL = "dark_metal"
    # Interior
    PAINTED_PLASTER = "painted_plaster"
    WOOD_FLOORING = "wood_flooring"
    CARPET = "carpet"
    TILE = "tile"
    # Roof
    SLATE = "slate"
    CLAY_TILE = "clay_tile"
    STANDING_SEAM_METAL = "standing_seam_metal"
    FLAT_ROOFING = "flat_roofing"
    # General
    GLASS = "glass"
    ALUMINIUM = "aluminium"
    WOOD = "wood"
    # Landscape
    GRASS = "grass"
    GRAVEL = "gravel"
    PAVING = "paving"


class MaterialUse(StrEnum):
    EXTERIOR_WALL = "exterior_wall"
    INTERIOR = "interior"
    ROOF = "roof"
    JOINERY = "joinery"  # frames, doors, trim
    LANDSCAPE = "landscape"


MATERIAL_USES: dict[MaterialId, frozenset[MaterialUse]] = {
    MaterialId.BRICK: frozenset({MaterialUse.EXTERIOR_WALL, MaterialUse.INTERIOR}),
    MaterialId.WHITE_RENDER: frozenset({MaterialUse.EXTERIOR_WALL}),
    MaterialId.CONCRETE: frozenset({MaterialUse.EXTERIOR_WALL, MaterialUse.INTERIOR, MaterialUse.LANDSCAPE}),
    MaterialId.TIMBER_CLADDING: frozenset({MaterialUse.EXTERIOR_WALL}),
    MaterialId.DARK_METAL: frozenset({MaterialUse.EXTERIOR_WALL, MaterialUse.JOINERY, MaterialUse.ROOF}),
    MaterialId.PAINTED_PLASTER: frozenset({MaterialUse.INTERIOR}),
    MaterialId.WOOD_FLOORING: frozenset({MaterialUse.INTERIOR}),
    MaterialId.CARPET: frozenset({MaterialUse.INTERIOR}),
    MaterialId.TILE: frozenset({MaterialUse.INTERIOR}),
    MaterialId.SLATE: frozenset({MaterialUse.ROOF}),
    MaterialId.CLAY_TILE: frozenset({MaterialUse.ROOF}),
    MaterialId.STANDING_SEAM_METAL: frozenset({MaterialUse.ROOF, MaterialUse.EXTERIOR_WALL}),
    MaterialId.FLAT_ROOFING: frozenset({MaterialUse.ROOF}),
    MaterialId.GLASS: frozenset({MaterialUse.JOINERY}),
    MaterialId.ALUMINIUM: frozenset({MaterialUse.JOINERY}),
    MaterialId.WOOD: frozenset({MaterialUse.JOINERY, MaterialUse.INTERIOR}),
    MaterialId.GRASS: frozenset({MaterialUse.LANDSCAPE}),
    MaterialId.GRAVEL: frozenset({MaterialUse.LANDSCAPE}),
    MaterialId.PAVING: frozenset({MaterialUse.LANDSCAPE}),
}


class MaterialRef(SpecModel):
    """A material plus an optional colour override, e.g. a darker brick.

    Accepts the shorthand "brick" as well as {"id": "brick", "colour": "#7a3b2e"}.
    """

    id: MaterialId
    colour: HexColour | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        return {"id": data} if isinstance(data, str) else data


def material(material_id: MaterialId, colour: str | None = None) -> MaterialRef:
    return MaterialRef(id=material_id, colour=colour)
