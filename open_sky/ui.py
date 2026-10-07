# SPDX-License-Identifier: GPL-3.0-or-later
"""Panels in Sidebar (N) > Sky and in World Properties."""

import math

import bpy

from . import rig, weather

SECTIONS = {
    "SUN": ["Sun Strength", "Sun Temperature", "Sun Tint", "Sun Size", "Sun Disc", "Sun Glow"],
    "ATMOSPHERE": ["Sky Brightness", "Air Density", "Ozone", "Haze Density", "Haze Color",
                   "Haze Anisotropy", "Horizon Fog", "Multiple Scattering",
                   "Ground", "Ground Color"],
    "MOON": ["Moon Size", "Moon Brightness", "Moon Light", "Moon Color", "Moon Detail",
             "Moon Glow", "Earthshine"],
    "NIGHT": ["Night Brightness", "Night Color", "Star Density", "Star Brightness",
              "Star Size", "Star Colors", "Twinkle", "Milky Way", "Milky Way Width",
              "Dust Lanes", "Latitude", "Sky Rotation", "Show Pole"],
    "CLOUDS": ["Cloud Coverage", "Cloud Density", "Cloud Height", "Cloud Thickness",
               "Cloud Scale", "Cloud Puffiness", "Cloud Darkness", "Cloud Color",
               "Cloud Evolution", "Cloud Distance", "Cloud Shadow",
               "Cirrus", "Cirrus Height", "Cirrus Scale"],
    "WEATHER": ["Wind Speed", "Wind Direction", "Rain", "Snow", "Lightning",
                "Rainbow", "Ice Halo"],
    "AURORA": ["Aurora", "Aurora Low Color", "Aurora High Color", "Aurora Height",
               "Aurora Thickness", "Aurora Scale", "Aurora Waviness", "Aurora Coverage",
               "Aurora Speed", "Aurora Rotation"],
}


def _world(context):
    w = context.scene.world
    return w if rig.is_sky_world(w) else None


def draw_inputs(layout, node, names):
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = True
    for name in names:
        s = node.inputs.get(name)
        if s is None or s.is_linked:
            continue
        col.prop(s, "default_value", text=name)


def _id_prop(layout, ob, key, text):
    if ob is not None and key in ob:
        layout.prop(ob, f'["{key}"]', text=text)


def draw_main(layout, context):
    world = _world(context)
    if world is None:
        layout.operator("open_sky.add", icon="WORLD")
        layout.label(text="Creates a new world and two lamps", icon="INFO")
        return
    settings = context.scene.open_sky
    layout.prop(settings, "preset", text="Preset")

    sun = rig.sun_object(world)
    box = layout.box()
    row = box.row(align=True)
    row.label(text="Sun Position", icon="LIGHT_SUN")
    row.operator("open_sky.select_lamp", text="", icon="RESTRICT_SELECT_OFF").which = "SUN"
    row.operator("open_sky.key_sun", text="", icon="KEY_HLT")
    box.prop(settings, "time_of_day")
    col = box.column(align=True)
    col.use_property_split = True
    col.use_property_decorate = False
    if settings.time_of_day:
        _id_prop(col, sun, rig.HOUR, "Hour")
        _id_prop(col, sun, rig.DAY, "Day of Year")
        _id_prop(col, sun, rig.LAT, "Latitude")
    elif sun is not None:
        col.prop(settings, "sun_elevation")
        col.prop(settings, "sun_azimuth")
    if sun is None:
        box.label(text="Sun lamp missing: press Rebuild Sky", icon="ERROR")

    z = rig.sky_node(world).inputs["Sun Direction"].default_value[2]
    el = math.degrees(math.asin(max(-1.0, min(1.0, z))))
    state = "Daylight" if el > 0.0 else ("Twilight" if el > -12.0 else "Night")
    layout.label(text=f"{state}: sun {abs(el):.0f}° {'above' if el >= 0 else 'below'} horizon",
                 icon="OUTLINER_OB_LIGHT" if el > 0.0 else "HIDE_ON")
    if settings.time_of_day and sun is not None:
        note = _polar_note(sun)
        if note:
            box = layout.box()
            for i, line in enumerate(note):
                box.label(text=line, icon="ERROR" if i == 0 else "BLANK1")


def _polar_note(sun):
    """Explain midnight sun / polar night for the current date and latitude."""
    if rig.DAY not in sun or rig.LAT not in sun:
        return None
    decl = -0.40911 * math.cos(0.017214 * (sun[rig.DAY] + 10))
    lat = sun[rig.LAT]
    highest = 90.0 - math.degrees(abs(lat - decl))
    lowest = math.degrees(abs(lat + decl)) - 90.0
    if lowest > -0.5:
        return ["Midnight sun: the sun never sets",
                "on this day at this latitude.",
                "Pick a winter day for a night sky."]
    if highest < 0.0:
        return ["Polar night: the sun never rises",
                "on this day at this latitude."]
    return None


class _Base:
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return _world(context) is not None


def _make_panels(prefix, space, region, category=None, context_name=None):
    common = {"bl_space_type": space, "bl_region_type": region}
    if category:
        common["bl_category"] = category
    if context_name:
        common["bl_context"] = context_name
    root_id = f"{prefix}_PT_open_sky"

    def draw_root(self, context):
        draw_main(self.layout, context)

    def section(key, label, extra=None):
        def draw(self, context):
            node = rig.sky_node(_world(context))
            if extra:
                extra(self.layout, context)
            draw_inputs(self.layout, node, SECTIONS[key])
        return type(f"{prefix}_PT_open_sky_{key.lower()}", (_Base, bpy.types.Panel), {
            **common, "bl_label": label, "bl_parent_id": root_id, "draw": draw})

    def moon_extra(layout, context):
        world = _world(context)
        settings = context.scene.open_sky
        row = layout.row(align=True)
        row.prop(settings, "moon_follow")
        row.operator("open_sky.select_lamp", text="", icon="RESTRICT_SELECT_OFF").which = "MOON"
        if settings.moon_follow:
            col = layout.column(align=True)
            col.use_property_split = True
            moon = rig.moon_object(world)
            _id_prop(col, moon, rig.OFF_AZ, "Phase Offset")
            _id_prop(col, moon, rig.OFF_EL, "Height Offset")

    def weather_extra(layout, context):
        world = _world(context)
        settings = context.scene.open_sky
        layout.prop(settings, "light_shafts")
        if settings.light_shafts:
            draw_inputs(layout, rig.sky_node(world), ["Light Shafts"])

    def precipitation_draw(self, context):
        world = _world(context)
        ob = rig.weather_object(world)
        mod = ob.modifiers.get(weather.GROUP) if ob else None
        if mod is None or mod.node_group is None:
            self.layout.label(text="Press Rebuild Sky to add rain and snow", icon="INFO")
            return
        col = self.layout.column()
        col.use_property_split = True
        for name in weather.USER_INPUTS:
            owner, prop = weather.input_prop(mod, name)
            col.prop(owner, prop, text=name)
        col.label(text="The box of drops follows the scene camera", icon="CAMERA_DATA")

    def camera_draw(self, context):
        layout = self.layout
        scene = context.scene
        col = layout.column()
        col.use_property_split = True
        col.prop(scene.open_sky, "auto_exposure")
        if scene.open_sky.auto_exposure:
            _id_prop(col, scene, rig.EXPOSURE, "Day Exposure")
            _id_prop(col, scene, rig.BOOST, "Night Boost")
        else:
            col.prop(scene.view_settings, "exposure")
        col.prop(scene.view_settings, "view_transform")
        col.prop(scene.view_settings, "look")
        row = layout.row(align=True)
        row.operator("open_sky.reset", icon="LOOP_BACK")
        row.operator("open_sky.repair", icon="FILE_REFRESH")

    root = type(root_id, (bpy.types.Panel,), {
        **common, "bl_label": "Open Sky", "draw": draw_root})
    return [
        root,
        section("SUN", "Sun"),
        section("ATMOSPHERE", "Atmosphere"),
        section("MOON", "Moon", moon_extra),
        section("NIGHT", "Stars & Milky Way"),
        section("AURORA", "Aurora"),
        section("CLOUDS", "Clouds"),
        section("WEATHER", "Weather", weather_extra),
        type(f"{prefix}_PT_open_sky_precipitation", (_Base, bpy.types.Panel), {
            **common, "bl_label": "Rain & Snow Particles",
            "bl_parent_id": f"{prefix}_PT_open_sky_weather", "draw": precipitation_draw}),
        type(f"{prefix}_PT_open_sky_camera", (_Base, bpy.types.Panel), {
            **common, "bl_label": "Camera & Tools", "bl_parent_id": root_id,
            "draw": camera_draw}),
    ]


CLASSES = (
    _make_panels("VIEW3D", "VIEW_3D", "UI", category="Sky")
    + _make_panels("WORLD", "PROPERTIES", "WINDOW", context_name="world")
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
