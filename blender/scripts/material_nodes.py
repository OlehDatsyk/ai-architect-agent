"""Helpers for building shader node trees: sockets by name, maths, mixing, and the shared
world-space texture coordinates every procedural material uses."""

import bpy

WORLD_UV = "AIARCH_WorldUV"


def socket(node, key: str):
    """Find an input by identifier first, then by display name (names differ between versions)."""
    for s in node.inputs:
        if s.identifier == key:
            return s
    for s in node.inputs:
        if s.name == key:
            return s
    raise KeyError(f"{node.bl_idname} has no input {key!r}")


class Builder:
    """Wraps a node tree so recipes read as a short list of connections."""

    def __init__(self, tree) -> None:
        self.tree = tree
        self.x = 0

    def node(self, kind: str, **inputs):
        node = self.tree.nodes.new(kind)
        node.location = (self.x, 0)
        self.x -= 220
        for key, value in inputs.items():
            self.set(node, key, value)
        return node

    def set(self, node, key: str, value) -> None:
        target = socket(node, key)
        if hasattr(value, "is_output"):  # another node's output socket
            self.tree.links.new(value, target)
        else:
            target.default_value = value

    def math(self, operation: str, a, b=0.0):
        node = self.node("ShaderNodeMath")
        node.operation = operation
        for index, value in enumerate((a, b)):
            if hasattr(value, "is_output"):
                self.tree.links.new(value, node.inputs[index])
            else:
                node.inputs[index].default_value = value
        return node.outputs[0]

    def mix_colour(self, factor, a, b):
        node = self.node("ShaderNodeMix")
        node.data_type = "RGBA"
        self.set(node, "Factor_Float", factor)
        self.set(node, "A_Color", a)
        self.set(node, "B_Color", b)
        return node.outputs["Result"] if "Result" in node.outputs else node.outputs[2]

    def mix_value(self, factor, a, b):
        return self.math("ADD", self.math("MULTIPLY", a, self.math("SUBTRACT", 1.0, factor)), self.math("MULTIPLY", b, factor))


def world_uv(builder: Builder):
    """Output socket of the shared texture-coordinate group, added to this material."""
    group = bpy.data.node_groups.get(WORLD_UV) or _create_world_uv()
    node = builder.tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    return node.outputs[0]


def _create_world_uv():
    """World-space projection that follows each face:

        walls   U = along the wall, V = height
        floors  U = x, V = y
        slopes  U = along the slope's contour line, V blends height and plan position

    Because it uses world position, textures continue seamlessly across the many separate
    objects a building is made of, and stay true to scale (a brick is 215 mm everywhere)."""
    group = bpy.data.node_groups.new(WORLD_UV, "ShaderNodeTree")
    group.interface.new_socket("Vector", in_out="OUTPUT", socket_type="NodeSocketVector")
    b = Builder(group)
    out = b.node("NodeGroupOutput")
    geometry = b.node("ShaderNodeNewGeometry")
    pos = b.node("ShaderNodeSeparateXYZ")
    group.links.new(geometry.outputs["Position"], pos.inputs[0])
    nrm = b.node("ShaderNodeSeparateXYZ")
    group.links.new(geometry.outputs["Normal"], nrm.inputs[0])
    x, y, z = pos.outputs[0], pos.outputs[1], pos.outputs[2]
    ax, ay, az = (b.math("ABSOLUTE", nrm.outputs[i]) for i in range(3))
    horizontal = b.math("ADD", b.math("ADD", ax, ay), 1e-6)
    along = b.math("DIVIDE", b.math("ADD", b.math("MULTIPLY", x, ay), b.math("MULTIPLY", y, ax)), horizontal)
    across = b.math("DIVIDE", b.math("ADD", b.math("MULTIPLY", x, ax), b.math("MULTIPLY", y, ay)), horizontal)
    upright = b.math("MINIMUM", b.math("MULTIPLY", horizontal, 100.0), 1.0)  # 0 on flat floors, 1 otherwise
    u = b.mix_value(upright, x, along)
    plan_v = b.mix_value(upright, y, across)
    v = b.mix_value(az, z, plan_v)
    combine = b.node("ShaderNodeCombineXYZ")
    group.links.new(u, combine.inputs[0])
    group.links.new(v, combine.inputs[1])
    group.links.new(combine.outputs[0], out.inputs[0])
    return group
