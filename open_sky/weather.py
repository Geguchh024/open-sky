# SPDX-License-Identifier: GPL-3.0-or-later
"""Rain and snow: a Geometry Nodes box of falling drops that follows the camera.

Drops are anchored in world space (the box wraps around the camera position),
so moving the camera doesn't drag the rain along. Everything is animated by
the scene time, so it works without the add-on.
"""

import math

import bpy

from .nodekit import NB, find_output

GROUP = "OS Weather"
OBJECT = "OS Weather"
VERSION = 1
DAYLIGHT = "Daylight"  # value node in each material, driven by the sun height

INPUTS = [  # (name, socket type, default, min, max)
    ("Rain", "NodeSocketFloat", 0.0, 0.0, 1.0),
    ("Snow", "NodeSocketFloat", 0.0, 0.0, 1.0),
    ("Wind Speed", "NodeSocketFloat", 5.0, 0.0, 100.0),
    ("Wind Direction", "NodeSocketFloat", math.radians(45.0), -10.0, 10.0),
    ("Area", "NodeSocketFloat", 40.0, 1.0, 1000.0),
    ("Height", "NodeSocketFloat", 20.0, 1.0, 1000.0),
    ("Rain Drops", "NodeSocketInt", 40000, 0, 2000000),
    ("Snowflakes", "NodeSocketInt", 25000, 0, 2000000),
    ("Drop Length", "NodeSocketFloat", 0.3, 0.01, 5.0),
    ("Flake Size", "NodeSocketFloat", 0.012, 0.001, 1.0),
    ("Seed", "NodeSocketInt", 0, 0, 100000),
]
USER_INPUTS = ("Area", "Height", "Rain Drops", "Snowflakes", "Drop Length", "Flake Size", "Seed")


def _material(name, colour, cycles_setup, eevee_alpha, eevee_glow):
    """A material with a lit Cycles look and an unlit EEVEE look.

    Thousands of lit drops would each ask EEVEE for shadow pages ("Shadow
    buffer full"), so EEVEE gets an emissive version instead. Its brightness
    follows the `Daylight` value node, which the rig drives from the sun.
    """
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    nb = NB(tree)
    out = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    out.target = "CYCLES"
    bsdf = tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = colour
    daylight = nb.node("ShaderNodeValue", name=DAYLIGHT, label=DAYLIGHT)
    daylight.outputs[0].default_value = 1.0
    cycles_setup(bsdf, daylight.outputs[0], nb)

    glow = nb.node("ShaderNodeEmission")
    nb.set(glow, "Color", colour)
    nb.set(glow, "Strength", nb.mul(daylight.outputs[0], eevee_glow))
    mix = nb.node("ShaderNodeMixShader")
    nb.set(mix, "Fac", eevee_alpha)
    nb.link(nb.node("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    nb.link(glow.outputs[0], mix.inputs[2])
    eevee = nb.node("ShaderNodeOutputMaterial", target="EEVEE")
    nb.link(mix.outputs[0], eevee.inputs["Surface"])
    return mat


def _rain_cycles(bsdf, daylight, nb):
    bsdf.inputs["Roughness"].default_value = 0.05
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["Alpha"].default_value = 0.35


def _snow_cycles(bsdf, daylight, nb):
    bsdf.inputs["Roughness"].default_value = 0.6
    bsdf.inputs["Alpha"].default_value = 0.9
    # Flakes pass light through; without a little glow they read as dark
    # specks against a bright overcast sky. It fades out at night.
    bsdf.inputs["Emission Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    nb.set(bsdf, "Emission Strength", nb.mul(daylight, 0.6))


def _materials():
    rain = _material("OS Rain", (0.85, 0.9, 1.0, 1.0), _rain_cycles, 0.3, 0.5)
    snow = _material("OS Snow", (0.95, 0.97, 1.0, 1.0), _snow_cycles, 0.85, 1.2)
    return rain, snow


def _wrap(nb, value, centre, half):
    return nb.math("WRAP", value, nb.add(centre, half), nb.sub(centre, half))


def _falling(nb, inp, count, fall, seed_offset, sway):
    """Points falling at `fall` m/s with the wind, wrapped around the camera."""
    rand = nb.node("FunctionNodeRandomValue", data_type="FLOAT_VECTOR")
    nb.set(rand, "Min", (0.0, 0.0, 0.0))
    nb.set(rand, "Max", (1.0, 1.0, 1.0))
    nb.set(rand, "Seed", nb.add(inp["Seed"], seed_offset))
    rx, ry, rz = nb.sep(find_output(rand, "Value"))
    speed = nb.node("FunctionNodeRandomValue", data_type="FLOAT")
    nb.set(speed, "Min", 0.8)
    nb.set(speed, "Max", 1.2)
    nb.set(speed, "Seed", nb.add(inp["Seed"], seed_offset + 1))
    speed = find_output(speed, "Value")

    t = nb.node("GeometryNodeInputSceneTime").outputs["Seconds"]
    me = nb.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    nb.set(me, "Object", nb.node("GeometryNodeSelfObject").outputs[0])
    cx, cy, cz = nb.sep(me.outputs["Location"])

    wd = inp["Wind Direction"]
    wx = nb.mul(nb.math("SINE", wd), inp["Wind Speed"])
    wy = nb.mul(nb.math("COSINE", wd), inp["Wind Speed"])
    vz = nb.mul(speed, -fall)
    area, height = inp["Area"], inp["Height"]
    half_a, half_h = nb.mul(area, 0.5), nb.mul(height, 0.5)
    x = _wrap(nb, nb.add(nb.mul(rx, area), nb.mul(wx, t)), cx, half_a)
    y = _wrap(nb, nb.add(nb.mul(ry, area), nb.mul(wy, t)), cy, half_a)
    z = _wrap(nb, nb.add(nb.mul(rz, height), nb.mul(vz, t)), cz, half_h)
    local = nb.comb(nb.sub(x, cx), nb.sub(y, cy), nb.sub(z, cz))
    if sway:
        ph = nb.mul(rx, 2 * math.pi * 7.0)
        local = nb.vadd(local, nb.comb(nb.mul(nb.math("SINE", nb.add(nb.mul(t, 1.1), ph)), 0.35),
                                       nb.mul(nb.math("COSINE", nb.add(nb.mul(t, 0.8), ph)), 0.35),
                                       0.0))
    pts = nb.node("GeometryNodePoints")
    nb.set(pts, "Count", count)
    nb.set(pts, "Position", local)
    return pts.outputs[0], nb.comb(wx, wy, vz)


def build_group():
    ng = bpy.data.node_groups.get(GROUP)
    if ng is None:
        ng = bpy.data.node_groups.new(GROUP, "GeometryNodeTree")
    else:
        ng.nodes.clear()
        ng.interface.clear()
    ng.is_modifier = True
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    for name, kind, default, lo, hi in INPUTS:
        s = ng.interface.new_socket(name, in_out="INPUT", socket_type=kind)
        s.default_value = default
        s.min_value, s.max_value = lo, hi
        if name == "Wind Direction":
            s.subtype = "ANGLE"
    ng["os_version"] = VERSION
    nb = NB(ng)
    gin = nb.node("NodeGroupInput")
    gout = nb.node("NodeGroupOutput")
    inp = gin.outputs
    rain_mat, snow_mat = _materials()

    # Rain: thin streaks aligned with their velocity (fast drops blur into lines).
    count = nb.math("ROUND", nb.mul(inp["Rain Drops"], inp["Rain"]))
    pts, vel = _falling(nb, inp, count, 9.0, 0, sway=False)
    drop = nb.node("GeometryNodeMeshCylinder", fill_type="NONE")
    nb.set(drop, "Vertices", 4)
    nb.set(drop, "Radius", 0.0025)
    nb.set(drop, "Depth", inp["Drop Length"])
    align = nb.node("FunctionNodeAlignRotationToVector", axis="Z")
    nb.set(align, "Vector", vel)
    rain = nb.node("GeometryNodeInstanceOnPoints")
    nb.set(rain, "Points", pts)
    nb.set(rain, "Instance", drop.outputs["Mesh"])
    nb.set(rain, "Rotation", align.outputs[0])
    rain_set = nb.node("GeometryNodeSetMaterial")
    nb.set(rain_set, "Geometry", rain.outputs[0])
    rain_set.inputs["Material"].default_value = rain_mat

    # Snow: small tumbling flakes that drift and sway.
    count = nb.math("ROUND", nb.mul(inp["Snowflakes"], inp["Snow"]))
    pts, _ = _falling(nb, inp, count, 1.0, 101, sway=True)
    flake = nb.node("GeometryNodeMeshIcoSphere")
    nb.set(flake, "Radius", inp["Flake Size"])
    nb.set(flake, "Subdivisions", 1)
    spin = nb.node("FunctionNodeRandomValue", data_type="FLOAT_VECTOR")
    nb.set(spin, "Max", (6.3, 6.3, 6.3))
    size = nb.node("FunctionNodeRandomValue", data_type="FLOAT")
    nb.set(size, "Min", 0.5)
    nb.set(size, "Max", 1.5)
    nb.set(size, "Seed", 7)
    snow = nb.node("GeometryNodeInstanceOnPoints")
    nb.set(snow, "Points", pts)
    nb.set(snow, "Instance", flake.outputs["Mesh"])
    nb.set(snow, "Rotation", find_output(spin, "Value"))
    nb.set(snow, "Scale", nb.comb(find_output(size, "Value"), find_output(size, "Value"),
                                  nb.mul(find_output(size, "Value"), 0.35)))
    snow_set = nb.node("GeometryNodeSetMaterial")
    nb.set(snow_set, "Geometry", snow.outputs[0])
    snow_set.inputs["Material"].default_value = snow_mat

    join = nb.node("GeometryNodeJoinGeometry")
    nb.link(rain_set.outputs[0], join.inputs[0])
    nb.link(snow_set.outputs[0], join.inputs[0])
    nb.link(join.outputs[0], gout.inputs[0])
    return ng


def ensure_group():
    ng = bpy.data.node_groups.get(GROUP)
    if ng is None or ng.get("os_version") != VERSION or len(ng.nodes) < 3:
        ng = build_group()
    return ng


def socket_id(ng, name):
    for item in ng.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            return item.identifier
    raise KeyError(name)


def input_prop(mod, name):
    """(owner, property) of a modifier input, for drawing and driving it.

    Blender 5 exposes inputs as mod.properties.inputs.<id>.value; older
    versions store them as ID properties on the modifier.
    """
    key = socket_id(mod.node_group, name)
    props = getattr(mod, "properties", None)
    inputs = getattr(props, "inputs", None)
    if inputs is not None and hasattr(inputs, key):
        return getattr(inputs, key), "value"
    return mod, f'["{key}"]'


def ensure_object(scene, collection):
    """The weather object: an empty mesh carrying the modifier, following the camera."""
    ng = ensure_group()
    ob = bpy.data.objects.get(OBJECT)
    if ob is None or ob.type != "MESH":
        ob = bpy.data.objects.new(OBJECT, bpy.data.meshes.new(OBJECT))
        collection.objects.link(ob)
    mod = ob.modifiers.get(GROUP)
    if mod is None:
        mod = ob.modifiers.new(GROUP, "NODES")
    mod.node_group = ng
    ob.visible_shadow = False  # thousands of drops would only add noise
    con = ob.constraints.get("Follow Camera")
    if con is None:
        con = ob.constraints.new("COPY_LOCATION")
        con.name = "Follow Camera"
    con.target = scene.camera
    return ob, mod
