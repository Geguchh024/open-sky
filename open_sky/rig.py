# SPDX-License-Identifier: GPL-3.0-or-later
"""World, sun lamp, moon lamp and the drivers that keep them in sync.

The sun lamp's rotation is the source of truth for the sun direction: rotate
or animate the lamp and the sky follows. All links are drivers with simple
expressions, so they work without the add-on and without "Auto Run Python
Scripts".
"""

import math

import bpy

from . import sky, weather

NODE_NAME = "Open Sky"
COLLECTION = "Open Sky"
SUN_NAME = "OS Sun"
MOON_NAME = "OS Moon"

# Custom properties stored on the lamps (they drive the rig, so they survive
# without the add-on and can be animated).
HOUR, DAY, LAT = "os_hour", "os_day", "os_latitude"
OFF_EL, OFF_AZ = "os_moon_elevation", "os_moon_azimuth"
EXPOSURE, BOOST = "os_exposure", "os_night_boost"


# -- lookups ---------------------------------------------------------------------------

def sky_node(world):
    if world is None or world.node_tree is None:
        return None
    n = world.node_tree.nodes.get(NODE_NAME)
    if n is not None and n.bl_idname == "ShaderNodeGroup" and n.node_tree is not None:
        return n
    return None


def is_sky_world(world):
    return sky_node(world) is not None


def _ptr(world, key):
    ob = world.get(key) if world is not None else None
    return ob if isinstance(ob, bpy.types.Object) else None


def sun_object(world):
    return _ptr(world, "os_sun")


def moon_object(world):
    return _ptr(world, "os_moon")


def weather_object(world):
    return _ptr(world, "os_weather")


def input_path(name, index=None):
    path = f'node_tree.nodes["{NODE_NAME}"].inputs["{name}"].default_value'
    return path if index is None else f"{path}[{index}]"


# -- driver helpers ---------------------------------------------------------------------

def _clear(owner, prop, index=-1):
    try:
        owner.driver_remove(prop, index)
    except TypeError:
        pass


def _drive(owner, prop, index, expr, variables):
    """variables: name -> ("prop", id_type, id, path) | ("rot", object, "ROT_X")."""
    fc = owner.driver_add(prop, index) if index is not None else owner.driver_add(prop)
    drv = fc.driver
    drv.type = "SCRIPTED"
    while drv.variables:
        drv.variables.remove(drv.variables[0])
    for name, spec in variables.items():
        var = drv.variables.new()
        var.name = name
        t = var.targets[0]
        if spec[0] == "rot":
            var.type = "TRANSFORMS"
            t.id = spec[1]
            t.transform_type = spec[2]
            t.transform_space = "WORLD_SPACE"
            t.rotation_mode = "XYZ"
        else:
            var.type = "SINGLE_PROP"
            t.id_type = spec[1]
            t.id = spec[2]
            t.data_path = spec[3]
    drv.expression = expr
    # A modifier left by driver_add would flatten the value to the keyframes.
    for m in list(fc.modifiers):
        fc.modifiers.remove(m)
    return fc


def _w(world, name, index=None):
    return ("prop", "WORLD", world, input_path(name, index))


def _rot(ob):
    return {"rx": ("rot", ob, "ROT_X"), "ry": ("rot", ob, "ROT_Y"), "rz": ("rot", ob, "ROT_Z")}


# Unit vector a lamp points away from (its local +Z) for an XYZ euler.
DIR_EXPR = (
    "cos(rz)*sin(ry)*cos(rx)+sin(rz)*sin(rx)",
    "sin(rz)*sin(ry)*cos(rx)-cos(rz)*sin(rx)",
    "cos(ry)*cos(rx)",
)


def _direction_drivers(world, name, ob):
    sock = sky_node(world).inputs[name]
    for i, expr in enumerate(DIR_EXPR):
        _drive(sock, "default_value", i, expr, _rot(ob))


def _airmass_expr(z):
    e = f"max({z},0)"
    return f"(1/({e}+{sky.AIRMASS_A}*exp(-{sky.AIRMASS_B}*{e})))"


# How much the clouds dim a lamp: a thick, full deck lets little direct light
# through; cirrus only takes the edge off.
CLOUD_DIM = "(1-k*c*c*(1-exp(-d*t)))*(1-0.3*k*r)"


def _cloud_vars(world):
    return {"k": _w(world, "Cloud Shadow"), "c": _w(world, "Cloud Coverage"),
            "d": _w(world, "Cloud Density"), "t": _w(world, "Cloud Thickness"),
            "r": _w(world, "Cirrus")}


def _sun_light_drivers(world, sun):
    light = sun.data
    light.use_temperature = True
    _drive(light, "energy", None, f"s*clamp((z+0.02)/0.06,0,1)*{CLOUD_DIM}",
           {"s": _w(world, "Sun Strength"), "z": _w(world, "Sun Direction", 2),
            **_cloud_vars(world)})
    _drive(light, "temperature", None, "a", {"a": _w(world, "Sun Temperature")})
    # Overcast skies soften the shadows.
    _drive(light, "angle", None, "a+k*c*c*0.6",
           {"a": _w(world, "Sun Size"), "k": _w(world, "Cloud Shadow"),
            "c": _w(world, "Cloud Coverage")})
    # Same transmittance as the sky shader (see sky.py) so the lamp matches.
    for i in range(3):
        ext = (f"({sky.RAYLEIGH[i]}*a+{sky.OZONE[i]}*o+{sky.MIE}*h*(2-c))")
        expr = f"t*exp(-{ext}*{_airmass_expr('z')})"
        _drive(light, "color", i, expr, {
            "t": _w(world, "Sun Tint", i), "a": _w(world, "Air Density"),
            "o": _w(world, "Ozone"), "h": _w(world, "Haze Density"),
            "c": _w(world, "Haze Color", i), "z": _w(world, "Sun Direction", 2),
        })


def _moon_light_drivers(world, moon):
    light = moon.data
    variables = {"l": _w(world, "Moon Light")}
    for i, axis in enumerate("xyz"):
        variables["s" + axis] = _w(world, "Sun Direction", i)
        variables["m" + axis] = _w(world, "Moon Direction", i)
    # Brightness follows the phase, sets with the moon, and fades out at dawn.
    expr = ("l*clamp((1-(sx*mx+sy*my+sz*mz))/2,0,1)"
            f"*clamp((mz+0.02)/0.06,0,1)*clamp((-sz-0.02)/0.15,0,1)*{CLOUD_DIM}")
    _drive(light, "energy", None, expr, {**variables, **_cloud_vars(world)})
    _drive(light, "angle", None, "a", {"a": _w(world, "Moon Size")})


def _weather_drivers(world, scene):
    ob = weather_object(world)
    if ob is None:
        return
    ob, mod = weather.ensure_object(scene, _collection(scene))
    for name in ("Rain", "Snow", "Wind Speed", "Wind Direction"):
        owner, prop = weather.input_prop(mod, name)
        _drive(owner, prop, None, "v", {"v": _w(world, name)})
    # Drops and flakes glow less as daylight fades (see weather._material).
    for mat_name in ("OS Rain", "OS Snow"):
        mat = bpy.data.materials.get(mat_name)
        node = mat.node_tree.nodes.get(weather.DAYLIGHT) if mat and mat.node_tree else None
        if node is not None:
            _drive(node.outputs[0], "default_value", None, "0.05+0.95*clamp((z+0.1)/0.25,0,1)",
                   {"z": _w(world, "Sun Direction", 2)})


def _time_driver(world, scene):
    fps = scene.render.fps / scene.render.fps_base
    _drive(sky_node(world).inputs["Time"], "default_value", None, f"frame/{fps:g}", {})


# -- optional modes ------------------------------------------------------------------------

def _set_prop(ob, key, value, **ui):
    if key not in ob:
        ob[key] = value
        ob.id_properties_ui(key).update(**ui)


def moon_follows(world):
    moon = moon_object(world)
    ad = moon.animation_data if moon else None
    return bool(ad and ad.drivers.find("rotation_euler", index=2))


def set_moon_follow(world, enable):
    sun, moon = sun_object(world), moon_object(world)
    if sun is None or moon is None:
        return
    for i in range(3):
        _clear(moon, "rotation_euler", i)
    if not enable:
        return
    _set_prop(moon, OFF_EL, 0.0, subtype="ANGLE", min=-math.pi, max=math.pi,
              description="Moon elevation relative to the point opposite the sun")
    _set_prop(moon, OFF_AZ, math.radians(25.0), subtype="ANGLE", min=-math.pi, max=math.pi,
              description="Moon azimuth offset from the point opposite the sun. "
                          "0 gives a full moon, 180 degrees a thin crescent")
    moon.rotation_mode = "XYZ"
    src = {"x": ("rot", sun, "ROT_X"), "y": ("rot", sun, "ROT_Y"), "z": ("rot", sun, "ROT_Z")}
    _drive(moon, "rotation_euler", 0, "x+3.14159265", src)
    _drive(moon, "rotation_euler", 1, "y+d",
           {**src, "d": ("prop", "OBJECT", moon, f'["{OFF_EL}"]')})
    _drive(moon, "rotation_euler", 2, "z+d",
           {**src, "d": ("prop", "OBJECT", moon, f'["{OFF_AZ}"]')})


def uses_time_of_day(world):
    sun = sun_object(world)
    ad = sun.animation_data if sun else None
    return bool(ad and ad.drivers.find("rotation_euler", index=2))


DECL = "(-0.40911*cos(0.017214*(d+10)))"
HOUR_ANGLE = "(0.261799*(h-12))"


def set_time_of_day(world, enable):
    sun, node = sun_object(world), sky_node(world)
    if sun is None or node is None:
        return
    for i in range(3):
        _clear(sun, "rotation_euler", i)
    _clear(node.inputs["Latitude"], "default_value")
    _clear(node.inputs["Sky Rotation"], "default_value")
    if not enable:
        return
    _set_prop(sun, HOUR, 12.0, min=0.0, max=24.0, soft_min=0.0, soft_max=24.0,
              description="Local solar time in hours")
    _set_prop(sun, DAY, 172.0, min=1.0, max=366.0, description="Day of the year")
    _set_prop(sun, LAT, node.inputs["Latitude"].default_value, subtype="ANGLE",
              min=-math.pi / 2, max=math.pi / 2, description="Latitude of the observer")
    variables = {"h": ("prop", "OBJECT", sun, f'["{HOUR}"]'),
                 "d": ("prop", "OBJECT", sun, f'["{DAY}"]'),
                 "l": ("prop", "OBJECT", sun, f'["{LAT}"]')}
    dec, ha = DECL, HOUR_ANGLE
    sin_el = f"(sin(l)*sin({dec})+cos(l)*cos({dec})*cos({ha}))"
    azimuth = (f"atan2(-cos({dec})*sin({ha}),"
               f"sin({dec})*cos(l)-cos({dec})*sin(l)*cos({ha}))")
    sun.rotation_mode = "XYZ"
    _drive(sun, "rotation_euler", 0, "0", {})
    _drive(sun, "rotation_euler", 1, f"acos(clamp({sin_el},-1,1))", variables)
    _drive(sun, "rotation_euler", 2, f"1.5707963-{azimuth}", variables)
    # Stars turn with local sidereal time; the sun's right ascension moves
    # through the year (0 at the March equinox, around day 80).
    _drive(node.inputs["Latitude"], "default_value", None, "l", variables)
    _drive(node.inputs["Sky Rotation"], "default_value", None,
           f"-({ha}+0.0172024*(d-80)+1.5707963)", variables)


def uses_light_shafts(world):
    node = sky_node(world)
    return bool(node and node.outputs["Volume"].is_linked)


def set_light_shafts(world, enable):
    node = sky_node(world)
    if node is None:
        return
    tree = world.node_tree
    out = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputWorld"), None)
    for link in list(node.outputs["Volume"].links):
        tree.links.remove(link)
    if enable and out is not None:
        tree.links.new(node.outputs["Volume"], out.inputs["Volume"])


def uses_auto_exposure(scene):
    ad = scene.animation_data
    return bool(ad and ad.drivers.find("view_settings.exposure"))


def set_auto_exposure(scene, world, enable):
    _clear(scene.view_settings, "exposure")
    if not enable or not is_sky_world(world):
        return
    _set_prop(scene, EXPOSURE, scene.view_settings.exposure, min=-10.0, max=10.0,
              description="Camera exposure in daylight")
    _set_prop(scene, BOOST, 3.0, min=0.0, max=15.0,
              description="Extra exposure in stops once the sun has set")
    _drive(scene.view_settings, "exposure", None,
           "b+k*(1-clamp((z+0.1)/0.15,0,1))",
           {"b": ("prop", "SCENE", scene, f'["{EXPOSURE}"]'),
            "k": ("prop", "SCENE", scene, f'["{BOOST}"]'),
            "z": _w(world, "Sun Direction", 2)})


# -- sun helpers -------------------------------------------------------------------------

def sun_angles(ob):
    """(elevation, azimuth) in radians. Azimuth is clockwise from +Y (north)."""
    z = ob.matrix_world.col[2]
    return math.asin(max(-1.0, min(1.0, z[2]))), math.atan2(z[0], z[1])


def set_sun_angles(ob, elevation=None, azimuth=None):
    el, az = sun_angles(ob)
    el = el if elevation is None else elevation
    az = az if azimuth is None else azimuth
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = (0.0, math.pi / 2 - el, math.pi / 2 - az)


# -- building the rig ------------------------------------------------------------------------

def _collection(scene):
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    if scene.collection.children.get(coll.name) is None and coll not in scene.collection.children[:]:
        scene.collection.children.link(coll)
    return coll


def _lamp(scene, name, color, shadow_angle):
    ob = bpy.data.objects.get(name)
    if ob is None or ob.type != "LIGHT":
        light = bpy.data.lights.new(name, "SUN")
        ob = bpy.data.objects.new(name, light)
        _collection(scene).objects.link(ob)
        ob.location = (0.0, 0.0, 6.0 if name == SUN_NAME else 5.0)
    ob.data.type = "SUN"
    ob.data.color = color
    ob.data.angle = shadow_angle
    return ob


def snapshot(node):
    """Input values by name (undriven ones only)."""
    out = {}
    for s in node.inputs:
        if hasattr(s, "default_value"):
            v = s.default_value
            out[s.name] = tuple(v) if hasattr(v, "__len__") else v
    return out


def restore(node, values):
    for s in node.inputs:
        if s.name in values and hasattr(s, "default_value"):
            try:
                s.default_value = values[s.name]
            except (TypeError, ValueError):
                pass


def _wire_world(world, group):
    tree = world.node_tree
    out = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputWorld"), None)
    if out is None:
        out = tree.nodes.new("ShaderNodeOutputWorld")
    node = tree.nodes.get(NODE_NAME)
    if node is None:
        node = tree.nodes.new("ShaderNodeGroup")
        node.name = NODE_NAME
        node.label = NODE_NAME
        node.width = 240
    node.node_tree = group
    node.location = (out.location.x - 320, out.location.y)
    tree.links.new(node.outputs["Background"], out.inputs["Surface"])
    return node


def connect(world, scene):
    """(Re)create every driver of the rig."""
    sun, moon = sun_object(world), moon_object(world)
    time_mode = uses_time_of_day(world)
    follow = moon_follows(world)
    _direction_drivers(world, "Sun Direction", sun)
    _direction_drivers(world, "Moon Direction", moon)
    _time_driver(world, scene)
    _sun_light_drivers(world, sun)
    _moon_light_drivers(world, moon)
    if weather_object(world) is None:
        world["os_weather"] = weather.ensure_object(scene, _collection(scene))[0]
    _weather_drivers(world, scene)
    set_moon_follow(world, follow)
    set_time_of_day(world, time_mode)


def create(scene, world=None):
    """Make `world` (or a new world) an Open Sky world with its lamps."""
    group = sky.ensure_groups()
    if world is None:
        world = bpy.data.worlds.new("Open Sky")
    world.use_nodes = True
    fresh = sky_node(world) is None
    _wire_world(world, group)
    scene.world = world

    sun = sun_object(world) or _lamp(scene, SUN_NAME, (1.0, 1.0, 1.0), math.radians(0.545))
    moon = moon_object(world) or _lamp(scene, MOON_NAME, (0.72, 0.82, 1.0), math.radians(1.0))
    sun.data.use_shadow = moon.data.use_shadow = True
    world["os_sun"] = sun
    world["os_moon"] = moon
    if fresh:
        set_sun_angles(sun, math.radians(40.0), math.radians(160.0))
        set_moon_follow(world, True)
    connect(world, scene)
    return world


def upgrade(world, scene):
    """Rebuild outdated groups, keeping the settings of this world."""
    _rebuild([world], scene)


def upgrade_file():
    if sky.groups_current() or bpy.data.node_groups.get(sky.MAIN) is None:
        return False
    _rebuild([w for w in bpy.data.worlds if is_sky_world(w)], bpy.context.scene)
    return True


def _rebuild(worlds, scene):
    # Rebuilding a group recreates its sockets, which drops the values and
    # links of the group nodes using it; save and restore both.
    saved = [(w, snapshot(sky_node(w)), uses_light_shafts(w)) for w in worlds]
    group = sky.ensure_groups(force=True)
    for w, values, shafts in saved:
        _wire_world(w, group)
        restore(sky_node(w), values)
        set_light_shafts(w, shafts)
        if sun_object(w) and moon_object(w):
            connect(w, scene)


def reset_inputs(node, keep=()):
    for name, spec in sky.INPUT_SPECS.items():
        if name in sky.DRIVEN_INPUTS or name in keep:
            continue
        sock = node.inputs.get(name)
        if sock is None or sock.is_linked:
            continue
        v = sky.default_value(name)
        if spec[1] == "color" and len(v) == 3:
            v = (*v, 1.0)
        sock.default_value = v
