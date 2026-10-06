"""The scene description sent to Blender. Data only: the Blender runner turns each element
into geometry with a predefined generator function and never executes anything from it."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.materials import MaterialId

SCENE_SCHEMA_VERSION = "1.0"

ObjectName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,59}$")]
ElementKind = Literal["ground", "slab", "wall", "room_floor", "door", "window", "stair", "balcony", "roof", "site", "vegetation"]
MAX_BOXES = 400
MAX_VERTICES = 5000


class Box3(BaseModel):
    """Axis-aligned box in metres. Blender uses the same axes: X width, Y depth (front y=0), Z up."""

    model_config = ConfigDict(extra="forbid")

    min: tuple[float, float, float]
    max: tuple[float, float, float]

    @property
    def size(self) -> tuple[float, float, float]:
        return tuple(b - a for a, b in zip(self.min, self.max))  # type: ignore[return-value]

    @property
    def volume(self) -> float:
        x, y, z = self.size
        return x * y * z

    def overlap_volume(self, other: "Box3") -> float:
        extent = [min(a2, b2) - max(a1, b1) for a1, a2, b1, b2 in zip(self.min, self.max, other.min, other.max)]
        return extent[0] * extent[1] * extent[2] if all(e > 0 for e in extent) else 0.0


def union(boxes: list[Box3]) -> Box3:
    return Box3(min=tuple(min(b.min[i] for b in boxes) for i in range(3)),  # type: ignore[arg-type]
                max=tuple(max(b.max[i] for b in boxes) for i in range(3)))  # type: ignore[arg-type]


class MeshData(BaseModel):
    """An explicit closed mesh, for shapes that are not boxes (roofs, gable ends).
    Faces list vertex indices counter-clockwise when seen from outside."""

    model_config = ConfigDict(extra="forbid")

    vertices: list[tuple[float, float, float]] = Field(min_length=4, max_length=MAX_VERTICES)
    faces: list[list[int]] = Field(min_length=4, max_length=MAX_VERTICES)

    def bounds(self) -> Box3:
        return Box3(min=tuple(min(v[i] for v in self.vertices) for i in range(3)),  # type: ignore[arg-type]
                    max=tuple(max(v[i] for v in self.vertices) for i in range(3)))  # type: ignore[arg-type]


# Every specification material, plus scene-only recipes for planting (not offered to Claude).
SceneRecipe = StrEnum("SceneRecipe", {**{m.name: m.value for m in MaterialId}, "FOLIAGE": "foliage", "BARK": "bark"})  # type: ignore[misc]


class SceneMaterial(BaseModel):
    """A procedural material: which recipe to build in Blender, and its base colour (which
    carries any colour override, such as a darker brick)."""

    model_config = ConfigDict(extra="forbid")

    name: ObjectName
    recipe: SceneRecipe  # type: ignore[valid-type]
    base_color: tuple[float, float, float]
    roughness: float = Field(0.7, ge=0, le=1)


class SceneCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ObjectName
    parent: ObjectName | None = None


class SceneElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ElementKind
    name: ObjectName
    collection: ObjectName
    # Either one or more boxes merged into a single object (a wall with openings is several
    # boxes), or an explicit mesh.
    boxes: list[Box3] = Field(default_factory=list, max_length=MAX_BOXES)
    mesh: MeshData | None = None
    material: ObjectName
    # Faces whose normal points along `inward` get `inner_material` instead (the plastered
    # inside face of an exterior wall).
    inner_material: ObjectName | None = None
    inward: Literal["+x", "-x", "+y", "-y"] | None = None
    # Plain metadata stored as custom properties on the Blender object (for later edits).
    tags: dict[str, str] = Field(default_factory=dict)


    @model_validator(mode="after")
    def _one_geometry(self) -> "SceneElement":
        if bool(self.boxes) == (self.mesh is not None):
            raise ValueError("an element needs either boxes or a mesh, not both")
        if (self.inner_material is None) != (self.inward is None):
            raise ValueError("inner_material and inward go together")
        return self

    @property
    def bounds(self) -> Box3:
        return self.mesh.bounds() if self.mesh else union(self.boxes)


Vec3 = tuple[float, float, float]
Colour = tuple[float, float, float]


class SceneCamera(BaseModel):
    """A camera at `location` looking at `target`, with the world's +Z as up."""

    model_config = ConfigDict(extra="forbid")

    name: ObjectName
    projection: Literal["perspective", "orthographic"]
    location: Vec3
    target: Vec3
    lens: float = Field(35.0, ge=8, le=300, description="Focal length in mm (perspective).")
    ortho_scale: float = Field(10.0, gt=0, le=1000, description="Width of view in metres (orthographic).")
    clip_end: float = Field(500.0, gt=1, le=10000)
    tags: dict[str, str] = Field(default_factory=dict)


class SceneLight(BaseModel):
    """A sun (only its direction matters: from `location` towards `target`) or an area light
    facing from `location` towards `target`."""

    model_config = ConfigDict(extra="forbid")

    name: ObjectName
    collection: ObjectName
    kind: Literal["sun", "area"]
    location: Vec3
    target: Vec3
    energy: float = Field(ge=0, le=100000, description="W/m² for suns, W for area lights.")
    colour: Colour = (1.0, 1.0, 1.0)
    size: float = Field(0.5, gt=0, le=20, description="Area light width (m), or sun angular diameter (degrees).")
    tags: dict[str, str] = Field(default_factory=dict)


class SceneWorld(BaseModel):
    """A gradient sky: horizon colour rising to zenith colour."""

    model_config = ConfigDict(extra="forbid")

    name: ObjectName
    horizon: Colour
    zenith: Colour
    ground: Colour
    strength: float = Field(ge=0, le=10)


class SceneViewLayer(BaseModel):
    """A Blender view layer that leaves out the listed collections (for floor-plan renders)."""

    model_config = ConfigDict(extra="forbid")

    name: ObjectName
    exclude: list[ObjectName]


class SceneRender(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_x: int = Field(1920, ge=16, le=8192)
    resolution_y: int = Field(1080, ge=16, le=8192)
    active_camera: ObjectName | None = None
    active_world: ObjectName | None = None
    # Collections that are not rendered by default (the evening lights, until switched on).
    hidden_collections: list[ObjectName] = Field(default_factory=list)

    @property
    def aspect(self) -> float:
        return self.resolution_x / self.resolution_y


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCENE_SCHEMA_VERSION
    project_name: str
    collections: list[SceneCollection]
    materials: list[SceneMaterial]
    elements: list[SceneElement]
    cameras: list[SceneCamera] = Field(default_factory=list)
    lights: list[SceneLight] = Field(default_factory=list)
    worlds: list[SceneWorld] = Field(default_factory=list)
    view_layers: list[SceneViewLayer] = Field(default_factory=list)
    render: SceneRender = Field(default_factory=SceneRender)
