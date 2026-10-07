# SPDX-License-Identifier: GPL-3.0-or-later
"""Open Sky: an open source procedural sky for Blender."""

import bpy
from bpy.app.handlers import persistent

from . import ops, props, rig, ui


@persistent
def _upgrade_on_load(*_args):
    """Rebuild sky node groups saved with an older add-on version."""
    try:
        rig.upgrade_file()
    except Exception as e:  # never block file loading
        print("Open Sky: upgrade failed:", e)


def register():
    props.register()
    ops.register()
    ui.register()
    bpy.app.handlers.load_post.append(_upgrade_on_load)


def unregister():
    if _upgrade_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_upgrade_on_load)
    ui.unregister()
    ops.unregister()
    props.unregister()
