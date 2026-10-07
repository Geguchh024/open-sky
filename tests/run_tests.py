# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test suite.

    blender -b --factory-startup --python tests/run_tests.py

Exits with a non-zero status when any test fails.
"""

import math
import os
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import open_sky  # noqa: E402

open_sky.register()
from open_sky import presets, rig, sky, ui, weather  # noqa: E402

TMP = tempfile.mkdtemp(prefix="os_tests_")
results = []


def test(fn):
    results.append(fn)
    return fn


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def new_sky():
    reset()
    scene = bpy.context.scene
    world = rig.create(scene)
    scene.frame_set(1)
    return scene, world


def refresh(scene, *changed):
    """Re-evaluate drivers; IDs whose custom properties changed must be tagged."""
    for idb in changed:
        idb.update_tag()
    scene.frame_set(scene.frame_current)


def all_drivers(world):
    ids = [world.node_tree, rig.sun_object(world), rig.sun_object(world).data,
           rig.moon_object(world), rig.moon_object(world).data, rig.weather_object(world),
           bpy.context.scene]
    for idb in ids:
        ad = idb.animation_data
        for fc in (ad.drivers if ad else []):
            yield idb, fc


def close(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def transmittance(node, z):
    """Python copy of the sun transmittance used by the shader and the lamp."""
    i = node.inputs
    e = max(z, 0.0)
    m = 1.0 / (e + sky.AIRMASS_A * math.exp(-sky.AIRMASS_B * e))
    out = []
    for c in range(3):
        ext = (sky.RAYLEIGH[c] * i["Air Density"].default_value
               + sky.OZONE[c] * i["Ozone"].default_value
               + sky.MIE * i["Haze Density"].default_value * (2 - i["Haze Color"].default_value[c]))
        out.append(i["Sun Tint"].default_value[c] * math.exp(-ext * m))
    return out


# ---------------------------------------------------------------------------

@test
def groups_build():
    reset()
    main = sky.ensure_groups()
    assert sky.groups_current()
    names = {s.name for s in main.interface.items_tree if s.item_type == "SOCKET" and s.in_out == "INPUT"}
    missing = set(sky.INPUT_SPECS) - names
    assert not missing, missing
    assert "Background" in [s.name for s in main.interface.items_tree
                            if s.item_type == "SOCKET" and s.in_out == "OUTPUT"]


@test
def rig_drivers_are_valid_and_need_no_python():
    scene, world = new_sky()
    assert scene.world == world and rig.is_sky_world(world)
    assert rig.sun_object(world).data.type == "SUN"
    count = 0
    for idb, fc in all_drivers(world):
        count += 1
        assert fc.driver.is_valid, (idb.name, fc.data_path, fc.array_index)
        assert fc.driver.is_simple_expression, (idb.name, fc.data_path, fc.driver.expression)
    assert count >= 22, count


@test
def sky_follows_sun_lamp():
    scene, world = new_sky()
    sun = rig.sun_object(world)
    node = rig.sky_node(world)
    for el, az in ((30, 0), (5, 90), (-10, 250), (70, 180)):
        rig.set_sun_angles(sun, math.radians(el), math.radians(az))
        refresh(scene)
        got_el, got_az = rig.sun_angles(sun)
        assert abs(math.degrees(got_el) - el) < 1e-3
        assert abs((math.degrees(got_az) - az + 180) % 360 - 180) < 1e-3
        assert close(node.inputs["Sun Direction"].default_value, sun.matrix_world.col[2][:3])
    # A tilted lamp (X rotation) must still match.
    sun.rotation_euler = (0.4, 0.7, -1.1)
    refresh(scene)
    assert close(node.inputs["Sun Direction"].default_value, sun.matrix_world.col[2][:3])


@test
def lamp_matches_sky_transmittance():
    scene, world = new_sky()
    sun = rig.sun_object(world)
    node = rig.sky_node(world)
    node.inputs["Haze Density"].default_value = 2.0
    node.inputs["Haze Color"].default_value = (1.0, 0.7, 0.4, 1.0)
    for el in (60, 15, 2):
        rig.set_sun_angles(sun, elevation=math.radians(el))
        refresh(scene)
        z = node.inputs["Sun Direction"].default_value[2]
        assert close(sun.data.color, transmittance(node, z)), (el, tuple(sun.data.color))
        fade = min(max((z + 0.02) / 0.06, 0.0), 1.0)
        assert abs(sun.data.energy - node.inputs["Sun Strength"].default_value * fade) < 1e-4
    assert abs(sun.data.temperature - node.inputs["Sun Temperature"].default_value) < 1e-3
    assert abs(sun.data.angle - node.inputs["Sun Size"].default_value) < 1e-6


@test
def day_to_night():
    scene, world = new_sky()
    sun, moon = rig.sun_object(world), rig.moon_object(world)
    rig.set_sun_angles(sun, math.radians(50))
    refresh(scene)
    noon = tuple(sun.data.color)
    assert sun.data.energy > 3.9 and moon.data.energy == 0.0
    rig.set_sun_angles(sun, math.radians(1))
    refresh(scene)
    low = tuple(sun.data.color)
    assert low[2] / low[0] < 0.5 * noon[2] / noon[0], (noon, low)  # sunset light is warmer
    rig.set_sun_angles(sun, math.radians(-30))
    refresh(scene)
    assert sun.data.energy == 0.0
    full = moon.data.energy
    assert full > 0.09, full  # near-full moon is up
    # Moon 10 degrees up, above the (set) sun: a thin crescent gives little light.
    moon[rig.OFF_AZ] = math.radians(180)
    moon[rig.OFF_EL] = math.radians(-20)
    refresh(scene, moon)
    assert 0.0 < moon.data.energy < 0.15 * full, moon.data.energy
    moon[rig.OFF_EL] = math.radians(-40)  # moon below the horizon
    refresh(scene, moon)
    assert moon.data.energy == 0.0


@test
def toggles_add_and_remove_drivers():
    scene, world = new_sky()
    s = scene.open_sky
    assert s.moon_follow and not s.time_of_day and not s.auto_exposure
    s.moon_follow = False
    assert not rig.moon_follows(world)
    s.moon_follow = True
    assert rig.moon_follows(world)
    s.time_of_day = True
    assert rig.uses_time_of_day(world)
    s.time_of_day = False
    assert not rig.uses_time_of_day(world)
    assert rig.sky_node(world).inputs["Latitude"].is_linked is False
    s.auto_exposure = True
    scene[rig.EXPOSURE] = 0.5
    scene[rig.BOOST] = 4.0
    rig.set_sun_angles(rig.sun_object(world), math.radians(40))
    refresh(scene, scene)
    assert abs(scene.view_settings.exposure - 0.5) < 1e-4
    rig.set_sun_angles(rig.sun_object(world), math.radians(-30))
    refresh(scene)
    assert abs(scene.view_settings.exposure - 4.5) < 1e-4
    s.auto_exposure = False
    assert not rig.uses_auto_exposure(scene)


@test
def time_of_day_places_sun_and_stars():
    scene, world = new_sky()
    scene.open_sky.time_of_day = True
    sun = rig.sun_object(world)
    node = rig.sky_node(world)
    lat = math.radians(45.0)
    sun[rig.LAT] = lat
    sun[rig.DAY] = 172.0  # June solstice
    refresh(scene, sun)
    decl = -0.40911 * math.cos(0.017214 * (172 + 10))
    radec = []
    for hour in (6.0, 9.0, 12.0, 15.0, 18.0):
        sun[rig.HOUR] = hour
        refresh(scene, sun)
        el, az = rig.sun_angles(sun)
        if hour == 12.0:
            assert abs(el - (math.pi / 2 - lat + decl)) < 1e-3, math.degrees(el)
            assert abs(abs(az) - math.pi) < 1e-3  # due south
        if hour == 9.0:
            assert 0 < az < math.pi  # morning sun in the east
        assert abs(node.inputs["Latitude"].default_value - lat) < 1e-6
        # Shader's celestial frame: tilt by 90 - latitude, spin by -rotation.
        tilt = Matrix.Rotation(math.pi / 2 - lat, 3, "X")
        spin = Matrix.Rotation(-node.inputs["Sky Rotation"].default_value, 3, "Z")
        v = spin @ tilt @ Vector(node.inputs["Sun Direction"].default_value)
        radec.append((math.atan2(v.y, v.x), math.asin(v.z)))
    # The sun stays at a fixed place among the stars during the day.
    for ra, dec in radec:
        assert abs(dec - decl) < 1e-3, (math.degrees(dec), math.degrees(decl))
        assert abs((ra - radec[0][0] + math.pi) % (2 * math.pi) - math.pi) < 1e-3


@test
def presets_apply():
    scene, world = new_sky()
    node = rig.sky_node(world)
    for pid, _, _, data in presets.PRESETS:
        assert bpy.ops.open_sky.apply_preset(preset=pid) == {"FINISHED"}, pid
        for name, v in presets.converted(data.get("values", {})).items():
            got = node.inputs[name].default_value
            got = tuple(got) if hasattr(got, "__len__") else (got,)
            want = tuple(v) if hasattr(v, "__len__") else (v,)
            assert close(got, want, 1e-5), (pid, name)
        refresh(scene)
        el, _ = rig.sun_angles(rig.sun_object(world))
        assert abs(math.degrees(el) - data["sun"][0]) < 1e-3, pid
    scene.open_sky.time_of_day = True
    assert bpy.ops.open_sky.apply_preset(preset="AURORA") == {"FINISHED"}
    assert abs(rig.sun_object(world)[rig.HOUR] - 23.0) < 1e-6


@test
def upgrade_keeps_settings():
    scene, world = new_sky()
    node = rig.sky_node(world)
    node.inputs["Haze Density"].default_value = 2.5
    node.inputs["Aurora Low Color"].default_value = (0.1, 0.2, 0.3, 1.0)
    for name in sky.ALL_GROUPS:
        bpy.data.node_groups[name]["os_version"] = 0
    assert rig.upgrade_file()
    assert sky.groups_current()
    node = rig.sky_node(world)
    assert abs(node.inputs["Haze Density"].default_value - 2.5) < 1e-6
    assert close(node.inputs["Aurora Low Color"].default_value, (0.1, 0.2, 0.3, 1.0))
    for idb, fc in all_drivers(world):
        assert fc.driver.is_valid, (idb.name, fc.data_path)


@test
def works_without_addon():
    scene, world = new_sky()
    path = os.path.join(TMP, "no_addon.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    open_sky.unregister()
    try:
        bpy.ops.wm.open_mainfile(filepath=path)
        scene = bpy.context.scene
        world = scene.world
        sun = world["os_sun"]
        rig.set_sun_angles(sun, math.radians(-20))
        refresh(scene)
        assert sun.data.energy == 0.0
        rig.set_sun_angles(sun, math.radians(30))
        refresh(scene)
        assert sun.data.energy > 3.9
        z = world.node_tree.nodes[rig.NODE_NAME].inputs["Sun Direction"].default_value[2]
        assert abs(z - 0.5) < 1e-3, z
    finally:
        open_sky.register()


@test
def aurora_preset_is_dark_in_time_of_day_mode():
    # Regression: at 68 degrees north in June the sun never sets, so the
    # Aurora preset showed daylight with Time of Day on.
    scene, world = new_sky()
    scene.open_sky.time_of_day = True
    assert bpy.ops.open_sky.apply_preset(preset="AURORA") == {"FINISHED"}
    sun = rig.sun_object(world)
    refresh(scene, sun)
    el, _ = rig.sun_angles(sun)
    assert math.degrees(el) < -18, math.degrees(el)
    assert ui._polar_note(sun) is None
    sun[rig.DAY] = 172.0
    assert "Midnight sun" in ui._polar_note(sun)[0]
    sun[rig.DAY] = 355.0
    assert "Polar night" in ui._polar_note(sun)[0]


@test
def clouds_dim_and_soften_the_sun():
    scene, world = new_sky()
    sun = rig.sun_object(world)
    rig.set_sun_angles(sun, math.radians(45))
    refresh(scene)
    clear_energy, clear_angle = sun.data.energy, sun.data.angle
    assert bpy.ops.open_sky.apply_preset(preset="OVERCAST") == {"FINISHED"}
    rig.set_sun_angles(sun, math.radians(45))
    refresh(scene)
    assert sun.data.energy < 0.1 * clear_energy, sun.data.energy
    assert sun.data.angle > clear_angle + 0.3
    rig.sky_node(world).inputs["Cloud Shadow"].default_value = 0.0
    refresh(scene)
    assert abs(sun.data.energy - clear_energy) < 1e-4


def _instances(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return sum(1 for inst in dg.object_instances
               if inst.is_instance and inst.parent and inst.parent.original == ob)


@test
def rain_and_snow_particles():
    scene, world = new_sky()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    bpy.ops.open_sky.repair()  # re-targets the weather box to the new camera
    ob = rig.weather_object(world)
    assert ob.constraints["Follow Camera"].target == cam
    node = rig.sky_node(world)
    mod = ob.modifiers[weather.GROUP]
    owner, prop = weather.input_prop(mod, "Rain Drops")
    setattr(owner, prop, 500)
    owner, prop = weather.input_prop(mod, "Snowflakes")
    setattr(owner, prop, 300)
    mod.show_viewport = False  # Blender 5.2 doesn't re-evaluate on these sets
    mod.show_viewport = True
    refresh(scene)
    assert _instances(ob) == 0
    node.inputs["Rain"].default_value = 1.0
    refresh(scene)
    assert _instances(ob) == 500, _instances(ob)
    node.inputs["Snow"].default_value = 0.5
    refresh(scene)
    assert _instances(ob) == 650, _instances(ob)


@test
def light_shafts_toggle():
    scene, world = new_sky()
    out = next(n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeOutputWorld")
    assert not out.inputs["Volume"].is_linked
    scene.open_sky.light_shafts = True
    assert out.inputs["Volume"].is_linked and scene.open_sky.light_shafts
    scene.open_sky.light_shafts = False
    assert not out.inputs["Volume"].is_linked


@test
def upgrade_from_first_release_adds_weather():
    scene, world = new_sky()
    scene.open_sky.light_shafts = True
    bpy.data.objects.remove(rig.weather_object(world))
    del world["os_weather"]
    for name in sky.ALL_GROUPS:
        bpy.data.node_groups[name]["os_version"] = 1
    assert rig.upgrade_file()
    out = next(n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeOutputWorld")
    assert out.inputs["Surface"].is_linked and out.inputs["Volume"].is_linked
    assert rig.weather_object(world) is not None
    for idb, fc in all_drivers(world):
        assert fc.driver.is_valid, (idb.name, fc.data_path)


def _render(scene, name):
    scene.render.filepath = os.path.join(TMP, name)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(scene.render.filepath + ".png")
    px = list(img.pixels)
    n = len(px) // 4
    mean = [sum(px[c::4]) / n for c in range(3)]
    bpy.data.images.remove(img)
    return mean


@test
def renders_in_both_engines():
    scene, world = new_sky()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "PANO"
    cam.data.panorama_type = "EQUIRECTANGULAR"
    cam.rotation_euler = (math.pi / 2, 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 64, 32
    scene.cycles.samples = 2
    sun = rig.sun_object(world)
    for engine in ("CYCLES", "BLENDER_EEVEE"):
        scene.render.engine = engine
        rig.set_sun_angles(sun, math.radians(50))
        refresh(scene)
        day = _render(scene, f"{engine}_day")
        rig.set_sun_angles(sun, math.radians(1))
        refresh(scene)
        dusk = _render(scene, f"{engine}_dusk")
        rig.set_sun_angles(sun, math.radians(-30))
        refresh(scene)
        night = _render(scene, f"{engine}_night")
        for m in (day, dusk, night):
            assert all(math.isfinite(c) for c in m), (engine, m)
        assert sum(day) > 5 * sum(night) > 0, (engine, day, night)
        assert day[2] > day[0], (engine, day)  # blue sky
        assert dusk[0] / dusk[2] > day[0] / day[2], (engine, day, dusk)  # warmer at dusk
        node = rig.sky_node(world)
        rig.set_sun_angles(sun, math.radians(50))
        node.inputs["Cloud Coverage"].default_value = 1.0
        node.inputs["Cloud Density"].default_value = 3.0
        refresh(scene)
        grey = _render(scene, f"{engine}_overcast")
        node.inputs["Cloud Coverage"].default_value = 0.0
        assert all(math.isfinite(c) for c in grey) and sum(grey) > 0, (engine, grey)
        assert sum(grey) < sum(day), (engine, day, grey)
        if engine == "CYCLES":  # EEVEE has no panoramic camera
            # An overcast sky is less blue than a clear one.
            assert grey[2] / grey[0] < day[2] / day[0], (engine, day, grey)


# ---------------------------------------------------------------------------

def main():
    failed = 0
    for fn in results:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(results) - failed}/{len(results)} passed")
    sys.exit(1 if failed else 0)


main()
