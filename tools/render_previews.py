# SPDX-License-Identifier: GPL-3.0-or-later
"""Render a preview of every preset and a contact sheet for the README.

    blender -b --factory-startup --python tools/render_previews.py [-- PRESET_ID ...]

Writes docs/images/presets/<ID>.png and docs/images/presets.png.
"""

import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402

import open_sky  # noqa: E402

open_sky.register()
from open_sky import ops, presets, rig  # noqa: E402

OUT = os.path.join(ROOT, "docs", "images")
# Presets shown on the README contact sheet (4 x 3).
SHEET = ("CLEAR_DAY", "PARTLY_CLOUDY", "SUNSET_CLOUDS", "GOLDEN_HOUR",
         "OVERCAST", "STORM", "RAINBOW", "CIRRUS",
         "MOONLIT", "STARRY", "AURORA", "SNOW")
WIDTH, HEIGHT = 640, 360

# Camera (azimuth, elevation, focal length) per preset; None looks at the sun.
VIEWS = {
    "CLEAR_DAY": (140, 8, 18),
    "MOONLIT": (150, 22, 24),
    "STARRY": (180, 28, 14),
    "AURORA": (0, 22, 14),
    "BLUE_HOUR": (270, 12, 18),
    "FAIR_CLOUDS": (130, 14, 16),
    "PARTLY_CLOUDY": (180, 14, 16),
    "RAINBOW": (80, 14, 14),
    "CIRRUS": (170, 22, 14),
    "OVERCAST": (150, 10, 18),
}


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    world = rig.create(scene)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.render.image_settings.file_format = "PNG"

    ground = bpy.data.materials.new("Ground")
    ground.use_nodes = True
    ground.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.2, 0.2, 0.2, 1)
    ground.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    bpy.ops.mesh.primitive_plane_add(size=400)
    bpy.context.object.data.materials.append(ground)
    for loc, size in (((0, 7, 1), 1.0), ((-2.6, 9, 0.7), 0.7), ((2.4, 8, 0.5), 0.5)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=size, location=loc, segments=48, ring_count=24)
        bpy.ops.object.shade_smooth()

    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene, world, cam


def aim(cam, az, el, lens):
    """Point the camera; the spheres are kept in front of it."""
    az, el = math.radians(az), math.radians(el)
    cam.data.lens = lens
    cam.location = (-7 * math.sin(az), 8 - 7 * math.cos(az), 1.6)
    cam.rotation_euler = (math.pi / 2 + el, 0.0, -az)


def render(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def contact_sheet(paths, out, cols=4):
    tiles = []
    for p in paths:
        img = bpy.data.images.load(p)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(HEIGHT, WIDTH, 4)
        tiles.append(px)
        bpy.data.images.remove(img)
    rows = math.ceil(len(tiles) / cols)
    sheet = np.zeros((rows * HEIGHT, cols * WIDTH, 4), dtype=np.float32)
    sheet[..., 3] = 1.0
    for i, t in enumerate(tiles):
        r = rows - 1 - i // cols  # image rows start at the bottom
        c = i % cols
        sheet[r * HEIGHT:(r + 1) * HEIGHT, c * WIDTH:(c + 1) * WIDTH] = t
    img = bpy.data.images.new("sheet", cols * WIDTH, rows * HEIGHT, alpha=False)
    img.pixels[:] = sheet.ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ids = argv or [p[0] for p in presets.PRESETS]
    scene, world, cam = build_scene()
    os.makedirs(os.path.join(OUT, "presets"), exist_ok=True)
    paths = []
    for pid in ids:
        ops.apply_preset(world, pid)
        scene.frame_set(1)
        sun_el, sun_az = presets.PRESET_BY_ID[pid][3]["sun"]
        az, el, lens = VIEWS.get(pid, (sun_az - 25, 10, 18))
        aim(cam, az, el, lens)
        path = os.path.join(OUT, "presets", f"{pid}.png")
        render(scene, path)
        paths.append(path)
    if not argv:
        by_id = dict(zip(ids, paths))
        contact_sheet([by_id[i] for i in SHEET], os.path.join(OUT, "presets.png"))


main()
