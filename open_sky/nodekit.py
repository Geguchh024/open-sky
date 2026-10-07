# SPDX-License-Identifier: GPL-3.0-or-later
"""Small DSL for building shader node trees from Python.

Every helper accepts either plain Python values or node sockets for its
inputs and returns an output socket, so node graphs can be written like
ordinary expressions:

    nb = NB(tree)
    mu = nb.dot(view, sun)
    glow = nb.mul(nb.exp(nb.mul(mu, 8.0)), strength)
"""

import math

import bpy


def srgb_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def hex_color(h):
    """'#RRGGBB' -> linear RGBA tuple."""
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


def to_value(v):
    if isinstance(v, str):
        return hex_color(v)
    return v


def _is_socket(v):
    return isinstance(v, bpy.types.NodeSocket)


def _available(sockets):
    for s in sockets:
        if getattr(s, "is_unavailable", not getattr(s, "enabled", True)):
            continue
        yield s


def find_input(node, key):
    if isinstance(key, int):
        return list(_available(node.inputs))[key]
    for s in _available(node.inputs):
        if s.name == key or s.identifier == key:
            return s
    raise KeyError(f"{node.bl_idname} has no input {key!r}")


def find_output(node, key=0):
    if isinstance(key, int):
        return list(_available(node.outputs))[key]
    for s in _available(node.outputs):
        if s.name == key or s.identifier == key:
            return s
    raise KeyError(f"{node.bl_idname} has no output {key!r}")


class NB:
    """Node builder bound to a node tree."""

    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links

    # -- basics -----------------------------------------------------------
    def node(self, idname, inputs=None, **props):
        n = self.nodes.new(idname)
        for k, v in props.items():
            setattr(n, k, v)
        if inputs:
            for k, v in inputs.items():
                self.set(n, k, v)
        return n

    def set(self, node, key, value):
        if value is None:
            return
        sock = find_input(node, key)
        if _is_socket(value):
            self.links.new(value, sock)
            return
        value = to_value(value)
        if sock.type == "RGBA" and isinstance(value, (int, float)):
            value = (value, value, value, 1.0)
        elif sock.type == "RGBA" and len(value) == 3:
            value = (*value, 1.0)
        elif sock.type == "VECTOR" and isinstance(value, (int, float)):
            value = (value, value, value)
        elif sock.type == "VECTOR" and len(value) == 4:
            value = value[:3]
        elif sock.type == "VALUE" and isinstance(value, tuple):
            value = value[0]
        sock.default_value = value

    def link(self, out, inp):
        self.links.new(out, inp)

    # -- scalar math --------------------------------------------------------
    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.set(n, i, v)
        return n.outputs[0]

    def add(self, a, b, clamp=False):
        return self.math("ADD", a, b, clamp=clamp)

    def sub(self, a, b, clamp=False):
        return self.math("SUBTRACT", a, b, clamp=clamp)

    def mul(self, a, b, clamp=False):
        return self.math("MULTIPLY", a, b, clamp=clamp)

    def div(self, a, b, clamp=False):
        return self.math("DIVIDE", a, b, clamp=clamp)

    def madd(self, a, b, c, clamp=False):
        return self.math("MULTIPLY_ADD", a, b, c, clamp=clamp)

    def pow(self, a, b):
        return self.math("POWER", a, b)

    def exp(self, a):
        return self.math("EXPONENT", a)

    def sqrt(self, a):
        return self.math("SQRT", a)

    def min(self, a, b):
        return self.math("MINIMUM", a, b)

    def max(self, a, b):
        return self.math("MAXIMUM", a, b)

    def abs(self, a):
        return self.math("ABSOLUTE", a)

    def cos(self, a):
        return self.math("COSINE", a)

    def clamp01(self, a):
        return self.math("ADD", a, 0.0, clamp=True)

    def one_minus(self, a):
        return self.math("SUBTRACT", 1.0, a, clamp=True)

    def lerp(self, a, b, t):
        n = self.node("ShaderNodeMix", data_type="FLOAT", clamp_factor=True)
        self.set(n, "Factor", t)
        self.set(n, "A", a)
        self.set(n, "B", b)
        return find_output(n, "Result")

    def remap(self, x, a, b, c=0.0, d=1.0, clamp=True, interp="LINEAR"):
        n = self.node("ShaderNodeMapRange", interpolation_type=interp, clamp=clamp)
        for k, v in (("Value", x), ("From Min", a), ("From Max", b),
                     ("To Min", c), ("To Max", d)):
            self.set(n, k, v)
        return find_output(n, "Result")

    def smooth(self, x, lo, hi):
        """Smoothstep from lo..hi -> 0..1 (lo > hi gives a falling edge)."""
        return self.remap(x, lo, hi, 0.0, 1.0, True, "SMOOTHSTEP")

    # -- vector math --------------------------------------------------------
    def vmath(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        ins = list(_available(n.inputs))
        if a is not None:
            self.set(n, 0, a)
        if b is not None and len(ins) > 1 and ins[1].type == "VECTOR":
            self.set(n, 1, b)
        if scale is not None:
            self.set(n, "Scale", scale)
        out = "Value" if op in {"DOT_PRODUCT", "LENGTH", "DISTANCE"} else "Vector"
        return find_output(n, out)

    def vadd(self, a, b):
        return self.vmath("ADD", a, b)

    def vsub(self, a, b):
        return self.vmath("SUBTRACT", a, b)

    def vmul(self, a, b):
        return self.vmath("MULTIPLY", a, b)

    def vdiv(self, a, b):
        return self.vmath("DIVIDE", a, b)

    def vscale(self, a, s):
        return self.vmath("SCALE", a, scale=s)

    def vmax(self, a, b):
        return self.vmath("MAXIMUM", a, b)

    def dot(self, a, b):
        return self.vmath("DOT_PRODUCT", a, b)

    def cross(self, a, b):
        return self.vmath("CROSS_PRODUCT", a, b)

    def length(self, a):
        return self.vmath("LENGTH", a)

    def normalize(self, a):
        return self.vmath("NORMALIZE", a)

    def vexp(self, v):
        """Per-channel exp() of a colour / vector."""
        x, y, z = self.sep(v)
        return self.comb(self.exp(x), self.exp(y), self.exp(z))

    def sep(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.set(n, 0, v)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def comb(self, x=0.0, y=0.0, z=0.0):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.set(n, i, v)
        return n.outputs[0]

    def rotate(self, vec, axis, angle, invert=False):
        """Rotate around a world axis ('X', 'Y' or 'Z') by angle (radians)."""
        n = self.node("ShaderNodeVectorRotate", rotation_type=f"{axis}_AXIS", invert=invert)
        self.set(n, "Vector", vec)
        self.set(n, "Center", (0.0, 0.0, 0.0))
        self.set(n, "Angle", angle)
        return n.outputs[0]

    def luminance(self, color):
        return self.dot(color, (0.2126, 0.7152, 0.0722))

    # -- colour -------------------------------------------------------------
    def mix(self, a, b, fac, blend="MIX", clamp=False):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend,
                      clamp_factor=True, clamp_result=clamp)
        self.set(n, "Factor", fac)
        self.set(n, "A", a)
        self.set(n, "B", b)
        return find_output(n, "Result")

    def ramp(self, fac, stops, interp="LINEAR"):
        """Colour ramp from [(position, colour), ...]; colour may be RGB or RGBA."""
        n = self.node("ShaderNodeValToRGB")
        cr = n.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (pos, col) in zip(cr.elements, stops):
            col = to_value(col)
            el.position = pos
            el.color = col if len(col) == 4 else (*col, 1.0)
        self.set(n, "Fac", fac)
        return n.outputs["Color"]

    def white(self, vec, dims="3D", w=None):
        n = self.node("ShaderNodeTexWhiteNoise", noise_dimensions=dims)
        if dims != "1D":
            self.set(n, "Vector", vec)
        if w is not None:
            self.set(n, "W", w)
        return n.outputs["Value"]

    def blackbody(self, kelvin):
        n = self.node("ShaderNodeBlackbody")
        self.set(n, "Temperature", kelvin)
        return n.outputs[0]

    # -- textures -------------------------------------------------------------
    def noise(self, vec, scale=5.0, detail=2.0, rough=0.5, dist=0.0,
              dims="3D", lac=2.0, w=None):
        n = self.node("ShaderNodeTexNoise", noise_dimensions=dims)
        if hasattr(n, "normalize"):
            n.normalize = True
        for k, v in (("Vector", vec), ("Scale", scale), ("Detail", detail),
                     ("Roughness", rough), ("Distortion", dist), ("Lacunarity", lac)):
            self.set(n, k, v)
        if w is not None:
            self.set(n, "W", w)
        return n

    def nfac(self, *args, **kw):
        return self.noise(*args, **kw).outputs["Fac"]

    def voronoi(self, vec, scale=5.0, feature="F1", rand=1.0, dims="3D"):
        n = self.node("ShaderNodeTexVoronoi", feature=feature,
                      voronoi_dimensions=dims, distance="EUCLIDEAN")
        if hasattr(n, "normalize"):
            n.normalize = False
        for k, v in (("Vector", vec), ("Scale", scale), ("Randomness", rand)):
            self.set(n, k, v)
        return n


# -- node groups -------------------------------------------------------------------

SOCKET_TYPES = {
    "float": "NodeSocketFloat",
    "color": "NodeSocketColor",
    "vector": "NodeSocketVector",
    "shader": "NodeSocketShader",
}


def _apply_spec(s, spec):
    kind, default = spec[1], spec[2]
    if kind == "float":
        lo, hi = spec[3], spec[4]
        if len(spec) > 5 and spec[5]:
            s.subtype = spec[5]
            if spec[5] == "ANGLE":
                default, lo, hi = math.radians(default), math.radians(lo), math.radians(hi)
        s.min_value, s.max_value = lo, hi
    default = to_value(default)
    if kind == "color" and len(default) == 3:
        default = (*default, 1.0)
    if kind != "shader":
        s.default_value = default


def new_group(name, inputs, outputs, version):
    """Create (or rebuild) a shader node group.

    inputs: list of (name, kind, default, min, max[, subtype]) or
            ("panel", title, [specs...]) for a collapsible panel.
            ANGLE defaults are given in degrees.
    outputs: list of (name, kind)
    Returns (group, NB, group_input_node, group_output_node).
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "ShaderNodeTree")
    else:
        ng.nodes.clear()
        ng.interface.clear()
    for oname, kind in outputs:
        ng.interface.new_socket(oname, in_out="OUTPUT", socket_type=SOCKET_TYPES[kind])

    def add_inputs(specs, parent=None):
        for spec in specs:
            if spec[0] == "panel":
                panel = ng.interface.new_panel(spec[1], default_closed=True)
                add_inputs(spec[2], panel)
                continue
            s = ng.interface.new_socket(spec[0], in_out="INPUT",
                                        socket_type=SOCKET_TYPES[spec[1]], parent=parent)
            _apply_spec(s, spec)

    add_inputs(inputs)
    nb = NB(ng)
    gin = nb.node("NodeGroupInput")
    gout = nb.node("NodeGroupOutput")
    ng["os_version"] = version
    return ng, nb, gin, gout


def group_node(nb, group):
    n = nb.node("ShaderNodeGroup")
    n.node_tree = group
    return n


def auto_layout(tree, dx=220, dy=190):
    """Column layout by longest-path depth so generated groups stay readable."""
    nodes = list(tree.nodes)
    incoming = {n: [] for n in nodes}
    for l in tree.links:
        incoming[l.to_node].append(l.from_node)
    depth = {}

    def d(n, stack=()):
        if n in depth:
            return depth[n]
        if n in stack:
            return 0
        val = 0 if not incoming[n] else 1 + max(d(p, stack + (n,)) for p in incoming[n])
        depth[n] = val
        return val

    cols = {}
    for n in nodes:
        cols.setdefault(d(n), []).append(n)
    for c, ns in cols.items():
        for i, n in enumerate(ns):
            n.location = (c * dx, -i * dy)
