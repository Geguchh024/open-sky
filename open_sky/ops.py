# SPDX-License-Identifier: GPL-3.0-or-later
import math

import bpy

from . import presets, rig, sky


def _sky_world(context):
    w = context.scene.world
    return w if rig.is_sky_world(w) else None


class OS_OT_add(bpy.types.Operator):
    bl_idname = "open_sky.add"
    bl_label = "Add Open Sky"
    bl_description = "Create an Open Sky world with a sun and a moon lamp"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        world = _sky_world(context)
        rig.create(context.scene, world)
        return {"FINISHED"}


class OS_OT_apply_preset(bpy.types.Operator):
    bl_idname = "open_sky.apply_preset"
    bl_label = "Apply Preset"
    bl_description = "Reset the sky and apply a built-in look"
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(items=presets.items())

    def execute(self, context):
        world = _sky_world(context)
        if world is None:
            world = rig.create(context.scene)
        apply_preset(world, self.preset)
        # Show the applied preset in the dropdown. Writing the stored index
        # directly skips the dropdown's update callback (which calls us).
        ids = [p[0] for p in presets.PRESETS]
        context.scene.open_sky["preset"] = ids.index(self.preset)
        return {"FINISHED"}


def apply_preset(world, preset_id):
    _, _, _, data = presets.PRESET_BY_ID[preset_id]
    node = rig.sky_node(world)
    rig.reset_inputs(node)
    values = presets.converted(data.get("values", {}))
    for name, v in values.items():
        node.inputs[name].default_value = v
    sun, moon = rig.sun_object(world), rig.moon_object(world)
    if rig.uses_time_of_day(world):
        sun[rig.HOUR] = data["hour"]
        sun[rig.DAY] = float(data.get("day", 172))
        sun[rig.LAT] = values.get("Latitude", sky.default_value("Latitude"))
        sun.update_tag()
    else:
        el, az = data["sun"]
        rig.set_sun_angles(sun, math.radians(el), math.radians(az))
    if moon is not None:
        el, az = data.get("moon", (0.0, 25.0))
        if not rig.moon_follows(world):
            rig.set_moon_follow(world, True)
        moon[rig.OFF_EL] = math.radians(el)
        moon[rig.OFF_AZ] = math.radians(az)
        moon.update_tag()


class OS_OT_select_lamp(bpy.types.Operator):
    bl_idname = "open_sky.select_lamp"
    bl_label = "Select Lamp"
    bl_description = "Select the lamp so it can be rotated or animated in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    which: bpy.props.EnumProperty(items=[("SUN", "Sun", ""), ("MOON", "Moon", "")])

    def execute(self, context):
        world = _sky_world(context)
        ob = rig.sun_object(world) if self.which == "SUN" else rig.moon_object(world)
        if ob is None or context.view_layer.objects.get(ob.name) is None:
            self.report({"WARNING"}, "The lamp is not in this view layer")
            return {"CANCELLED"}
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {"FINISHED"}


class OS_OT_key_sun(bpy.types.Operator):
    bl_idname = "open_sky.key_sun"
    bl_label = "Keyframe Sun"
    bl_description = "Insert a keyframe for the sun position (or the hour in Time of Day mode)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        world = _sky_world(context)
        sun = rig.sun_object(world)
        if sun is None:
            return {"CANCELLED"}
        if rig.uses_time_of_day(world):
            sun.keyframe_insert(f'["{rig.HOUR}"]')
        else:
            sun.keyframe_insert("rotation_euler")
        return {"FINISHED"}


class OS_OT_repair(bpy.types.Operator):
    bl_idname = "open_sky.repair"
    bl_label = "Rebuild Sky"
    bl_description = ("Rebuild the sky node groups and reconnect the lamps, "
                      "keeping the current settings")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        world = _sky_world(context)
        if world is None:
            return {"CANCELLED"}
        if rig.sun_object(world) is None or rig.moon_object(world) is None:
            rig.create(context.scene, world)
        rig.upgrade(world, context.scene)
        return {"FINISHED"}


class OS_OT_reset(bpy.types.Operator):
    bl_idname = "open_sky.reset"
    bl_label = "Reset Settings"
    bl_description = "Set every sky setting back to its default"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        world = _sky_world(context)
        if world is None:
            return {"CANCELLED"}
        rig.reset_inputs(rig.sky_node(world))
        return {"FINISHED"}


CLASSES = (OS_OT_add, OS_OT_apply_preset, OS_OT_select_lamp, OS_OT_key_sun,
           OS_OT_repair, OS_OT_reset)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
