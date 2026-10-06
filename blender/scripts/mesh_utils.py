"""Low-level geometry helpers shared by the generators."""

import bpy

# 8 corners of a unit box centred on the origin, and its 6 faces (outward normals).
_CORNERS = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


# Set by scene_builder before elements are created: name -> material, for inner faces.
inner_materials: dict = {}
_AXES = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0)}


def _assign_inner_faces(obj, material, inward: str) -> None:
    """Faces pointing into the building use the second material slot."""
    obj.data.materials.append(material)
    axis = _AXES[inward]
    for polygon in obj.data.polygons:
        if sum(n * a for n, a in zip(polygon.normal, axis)) > 0.9:
            polygon.material_index = 1


def create_element(element: dict, collection, material, kind: str):
    """One object from either a list of boxes (merged into one mesh) or an explicit mesh.
    The object's origin is the centre of its bounds, so it moves and scales naturally."""
    if element.get("mesh"):
        verts = [tuple(v) for v in element["mesh"]["vertices"]]
        faces = [tuple(f) for f in element["mesh"]["faces"]]
    else:
        verts, faces = [], []
        for box in element["boxes"]:
            lo, hi = box["min"], box["max"]
            base = len(verts)
            verts += [tuple(hi[i] if c > 0 else lo[i] for i, c in enumerate(corner)) for corner in _CORNERS]
            faces += [tuple(base + i for i in face) for face in _FACES]
    centre = [(min(v[i] for v in verts) + max(v[i] for v in verts)) / 2 for i in range(3)]
    local = [tuple(v[i] - centre[i] for i in range(3)) for v in verts]
    mesh = bpy.data.meshes.new(f"{element['name']}_Mesh")
    mesh.from_pydata(local, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(element["name"], mesh)
    obj.location = centre
    obj.data.materials.append(material)
    if element.get("inner_material"):
        _assign_inner_faces(obj, inner_materials[element["inner_material"]], element["inward"])
    obj["aiarch_kind"] = kind
    for key, value in element.get("tags", {}).items():
        obj[f"aiarch_{key}"] = value
    collection.objects.link(obj)
    return obj


def create_box(name: str, box_min, box_max, collection, material=None, tags: dict | None = None):
    """A box object whose origin is its centre, so it can be moved and scaled naturally in Blender."""
    size = [b - a for a, b in zip(box_min, box_max)]
    centre = [(a + b) / 2 for a, b in zip(box_min, box_max)]
    half = [s / 2 for s in size]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata([tuple(c * h for c, h in zip(corner, half)) for corner in _CORNERS], [], _FACES)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = centre
    if material is not None:
        obj.data.materials.append(material)
    for key, value in (tags or {}).items():
        obj[f"aiarch_{key}"] = value
    collection.objects.link(obj)
    return obj
