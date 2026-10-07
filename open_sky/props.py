# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene settings. Most of them are views onto the rig (lamp rotation, drivers),
so nothing here has to be kept in sync."""

import math

import bpy

from . import presets, rig


def _world(self):
    w = self.id_data.world
    return w if rig.is_sky_world(w) else None


def _sun(self):
    return rig.sun_object(_world(self))


def _get_elevation(self):
    sun = _sun(self)
    return rig.sun_angles(sun)[0] if sun else 0.0


def _set_elevation(self, value):
    sun = _sun(self)
    if sun and not rig.uses_time_of_day(_world(self)):
        rig.set_sun_angles(sun, elevation=value)


def _get_azimuth(self):
    sun = _sun(self)
    return rig.sun_angles(sun)[1] % (2 * math.pi) if sun else 0.0


def _set_azimuth(self, value):
    sun = _sun(self)
    if sun and not rig.uses_time_of_day(_world(self)):
        rig.set_sun_angles(sun, azimuth=value)


def _get_time(self):
    return rig.uses_time_of_day(_world(self))


def _set_time(self, value):
    world = _world(self)
    if world:
        rig.set_time_of_day(world, value)


def _get_follow(self):
    return rig.moon_follows(_world(self))


def _set_follow(self, value):
    world = _world(self)
    if world:
        rig.set_moon_follow(world, value)


def _get_exposure(self):
    return rig.uses_auto_exposure(self.id_data)


def _set_exposure(self, value):
    rig.set_auto_exposure(self.id_data, _world(self), value)


def _get_shafts(self):
    return rig.uses_light_shafts(_world(self))


def _set_shafts(self, value):
    world = _world(self)
    if world:
        rig.set_light_shafts(world, value)


def _preset_changed(self, context):
    bpy.ops.open_sky.apply_preset(preset=self.preset)


class OS_SceneSettings(bpy.types.PropertyGroup):
    preset: bpy.props.EnumProperty(
        name="Preset", items=presets.items(), update=_preset_changed,
        description="Apply a built-in look")
    sun_elevation: bpy.props.FloatProperty(
        name="Elevation", subtype="ANGLE", min=-math.pi / 2, max=math.pi / 2,
        get=_get_elevation, set=_set_elevation,
        description="Height of the sun above the horizon (rotates the sun lamp)")
    sun_azimuth: bpy.props.FloatProperty(
        name="Azimuth", subtype="ANGLE", min=0.0, max=2 * math.pi,
        get=_get_azimuth, set=_set_azimuth,
        description="Compass direction of the sun, clockwise from north (+Y)")
    time_of_day: bpy.props.BoolProperty(
        name="Time of Day", get=_get_time, set=_set_time,
        description="Place the sun and stars from hour, day of year and latitude")
    moon_follow: bpy.props.BoolProperty(
        name="Moon Follows Sun", get=_get_follow, set=_set_follow,
        description="Keep the moon opposite the sun plus an offset, so it rises "
                    "at night and its phase changes with the offset")
    light_shafts: bpy.props.BoolProperty(
        name="Light Shafts", get=_get_shafts, set=_set_shafts,
        description="Fill the world with a thin volume so the sun casts visible "
                    "rays through gaps (slower to render, especially in Cycles)")
    auto_exposure: bpy.props.BoolProperty(
        name="Night Exposure", get=_get_exposure, set=_set_exposure,
        description="Raise the camera exposure automatically after sunset")


def register():
    bpy.utils.register_class(OS_SceneSettings)
    bpy.types.Scene.open_sky = bpy.props.PointerProperty(type=OS_SceneSettings)


def unregister():
    del bpy.types.Scene.open_sky
    bpy.utils.unregister_class(OS_SceneSettings)
