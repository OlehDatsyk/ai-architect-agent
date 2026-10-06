"""Procedural materials, one recipe per material identifier. No image textures are used.

Each recipe receives the material's base colour (which carries any colour override, such as
a darker brick) and builds a node tree feeding a Principled BSDF. Only recipes listed in
RECIPES can be built; the scene validator rejects any other name.
"""

import bpy
from material_nodes import Builder, world_uv


def _shade(colour, factor: float):
    return tuple(min(max(c * factor, 0.0), 1.0) for c in colour) + (1.0,)


def _rgba(colour):
    return tuple(colour) + (1.0,)


def _units(builder, kind, uv, colour, alt, mortar, width, row, mortar_size, offset=0.5, scale=1.0):
    """Courses of bricks, tiles, boards or planks; returns (colour output, mortar mask output)."""
    node = builder.node(kind, Vector=uv, Color1=_rgba(colour), Color2=alt, Mortar=mortar, Scale=scale,
                        **{"Mortar Size": mortar_size, "Brick Width": width, "Row Height": row, "Mortar Smooth": 0.6})
    node.offset = offset
    node.offset_frequency = 2
    return node.outputs["Color"], node.outputs["Fac"]


def _bump(builder, bsdf, height, strength: float, distance: float = 0.01, invert: bool = False) -> None:
    node = builder.node("ShaderNodeBump", Strength=strength, Distance=distance, Height=height)
    node.invert = invert
    builder.set(bsdf, "Normal", node.outputs["Normal"])


def _noise(builder, uv, scale: float, detail: float = 6.0):
    node = builder.node("ShaderNodeTexNoise", Vector=uv, Scale=scale, Detail=detail)
    return node.outputs["Fac"]


def _grain(builder, uv, scale: float, distortion: float):
    node = builder.node("ShaderNodeTexWave", Vector=uv, Scale=scale, Distortion=distortion, Detail=2.0)
    node.wave_type = "BANDS"
    node.bands_direction = "Y"
    return node.outputs["Fac"]


def _coursed(b, bsdf, uv, base, *, width, row, mortar_size, mortar, alt=0.82, offset=0.5, roughness=0.8, bump=0.4, grain=None):
    colour, mask = _units(b, "ShaderNodeTexBrick", uv, base, _shade(base, alt), mortar, width, row, mortar_size, offset)
    if grain:
        colour = b.mix_colour(b.math("MULTIPLY", _grain(b, uv, *grain), 0.3), colour, _shade(base, 0.6))
    b.set(bsdf, "Base Color", colour)
    b.set(bsdf, "Roughness", roughness)
    _bump(b, bsdf, mask, bump, invert=True)


def _textured(b, bsdf, uv, base, *, scale, variation, roughness, bump, fine=None):
    noise = _noise(b, uv, scale)
    b.set(bsdf, "Base Color", b.mix_colour(noise, _rgba(base), _shade(base, variation)))
    b.set(bsdf, "Roughness", roughness)
    _bump(b, bsdf, _noise(b, uv, fine) if fine else noise, bump, distance=0.005)


def brick(b, bsdf, uv, base):
    _coursed(b, bsdf, uv, base, width=0.225, row=0.075, mortar_size=0.01, mortar=(0.55, 0.53, 0.5, 1), alt=0.78, roughness=0.85, bump=0.5)


def white_render(b, bsdf, uv, base):
    _textured(b, bsdf, uv, base, scale=4, variation=0.93, roughness=0.9, bump=0.06, fine=80)


def concrete(b, bsdf, uv, base):
    _textured(b, bsdf, uv, base, scale=3, variation=0.8, roughness=0.8, bump=0.12, fine=40)


def timber_cladding(b, bsdf, uv, base):
    _coursed(b, bsdf, uv, base, width=2.4, row=0.15, mortar_size=0.008, mortar=_shade(base, 0.35), alt=0.85, offset=0.37,
             roughness=0.7, bump=0.6, grain=(3.0, 6.0))


def dark_metal(b, bsdf, uv, base):
    b.set(bsdf, "Base Color", _rgba(base))
    b.set(bsdf, "Metallic", 0.85)
    b.set(bsdf, "Roughness", 0.35)


def painted_plaster(b, bsdf, uv, base):
    _textured(b, bsdf, uv, base, scale=6, variation=0.97, roughness=0.9, bump=0.03, fine=120)


def wood_flooring(b, bsdf, uv, base):
    _coursed(b, bsdf, uv, base, width=1.2, row=0.19, mortar_size=0.002, mortar=_shade(base, 0.5), alt=0.8, offset=0.3,
             roughness=0.35, bump=0.15, grain=(6.0, 8.0))


def carpet(b, bsdf, uv, base):
    _textured(b, bsdf, uv, base, scale=300, variation=0.85, roughness=1.0, bump=0.2)


def tile(b, bsdf, uv, base):
    _coursed(b, bsdf, uv, base, width=0.3, row=0.3, mortar_size=0.004, mortar=(0.85, 0.85, 0.83, 1), alt=0.96, offset=0.0,
             roughness=0.15, bump=0.3)


def slate(b, bsdf, uv, base):
    _coursed(b, bsdf, uv, base, width=0.5, row=0.25, mortar_size=0.006, mortar=_shade(base, 0.4), alt=0.75, roughness=0.55, bump=0.5)


def clay_tile(b, bsdf, uv, base):
    _coursed(b, bsdf, uv, base, width=0.3, row=0.25, mortar_size=0.006, mortar=_shade(base, 0.45), alt=0.82, roughness=0.7, bump=0.6)


def standing_seam_metal(b, bsdf, uv, base):
    # Very tall "bricks" leave only the vertical seams, every 0.5 m, raised rather than recessed.
    _, seams = _units(b, "ShaderNodeTexBrick", uv, base, _shade(base, 1.0), _shade(base, 1.2), 0.5, 100.0, 0.015, offset=0.0)
    b.set(bsdf, "Base Color", _rgba(base))
    b.set(bsdf, "Metallic", 0.6)
    b.set(bsdf, "Roughness", 0.4)
    _bump(b, bsdf, seams, 0.8)


def flat_roofing(b, bsdf, uv, base):
    _textured(b, bsdf, uv, base, scale=20, variation=0.8, roughness=0.95, bump=0.1)


def glass(b, bsdf, uv, base, material=None):
    b.set(bsdf, "Base Color", _rgba(base))
    b.set(bsdf, "Roughness", 0.02)
    b.set(bsdf, "IOR", 1.45)
    b.set(bsdf, "Transmission Weight", 1.0)
    # Cycles sees through glass by transmission; EEVEE needs real transparency as well (with the
    # blended render method set in create_material). Reflections keep it reading as glass.
    b.set(bsdf, "Alpha", 0.25)


def aluminium(b, bsdf, uv, base):
    b.set(bsdf, "Base Color", _rgba(base))
    b.set(bsdf, "Metallic", 1.0)
    b.set(bsdf, "Roughness", 0.3)


def wood(b, bsdf, uv, base):
    b.set(bsdf, "Base Color", b.mix_colour(_grain(b, uv, 8.0, 8.0), _rgba(base), _shade(base, 0.7)))
    b.set(bsdf, "Roughness", 0.5)


def grass(b, bsdf, uv, base):
    _textured(b, bsdf, uv, base, scale=2, variation=0.65, roughness=0.95, bump=0.3, fine=200)


def gravel(b, bsdf, uv, base):
    stones = b.node("ShaderNodeTexVoronoi", Vector=uv, Scale=25.0)
    b.set(bsdf, "Base Color", b.mix_colour(stones.outputs["Distance"], _rgba(base), _shade(base, 0.6)))
    b.set(bsdf, "Roughness", 0.9)
    _bump(b, bsdf, stones.outputs["Distance"], 0.6)


def paving(b, bsdf, uv, base):
    _coursed(b, bsdf, uv, base, width=0.6, row=0.6, mortar_size=0.008, mortar=_shade(base, 0.7), alt=0.9, roughness=0.8, bump=0.4)


def foliage(b, bsdf, uv, base):
    """Leafy canopy: clumpy colour from coarse noise and a strong, fine bump."""
    _textured(b, bsdf, uv, base, scale=1.5, variation=1.8, roughness=0.9, bump=0.5, fine=12)


def bark(b, bsdf, uv, base):
    _textured(b, bsdf, uv, base, scale=8, variation=0.6, roughness=0.95, bump=0.6, fine=30)


RECIPES = {
    "brick": brick, "white_render": white_render, "concrete": concrete, "timber_cladding": timber_cladding,
    "dark_metal": dark_metal, "painted_plaster": painted_plaster, "wood_flooring": wood_flooring, "carpet": carpet,
    "tile": tile, "slate": slate, "clay_tile": clay_tile, "standing_seam_metal": standing_seam_metal,
    "flat_roofing": flat_roofing, "glass": glass, "aluminium": aluminium, "wood": wood, "grass": grass,
    "gravel": gravel, "paving": paving, "foliage": foliage, "bark": bark,
}


def create_material(spec: dict):
    mat = bpy.data.materials.new(spec["name"])
    if mat.node_tree is None:  # Blender 4.x; in 5.x new materials already have a node tree
        mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    builder = Builder(tree)
    output = builder.node("ShaderNodeOutputMaterial")
    bsdf = builder.node("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    base = tuple(spec["base_color"])
    RECIPES[spec["recipe"]](builder, bsdf, world_uv(builder), base)
    if spec["recipe"] == "glass" and hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"  # see-through glass in EEVEE; BLENDED stalled headless EEVEE
    mat.diffuse_color = base + (0.3 if spec["recipe"] == "glass" else 1.0,)  # solid-view colour
    mat["aiarch_recipe"] = spec["recipe"]
    return mat


def create_materials(specs: list[dict]) -> dict:
    return {spec["name"]: create_material(spec) for spec in specs}
