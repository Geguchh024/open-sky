# SPDX-License-Identifier: GPL-3.0-or-later
"""Open Sky: an open source procedural sky for Blender."""

import threading

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


@persistent
def _prune_on_update(_scene, depsgraph):
    """Switch sky layers on and off as their strengths cross 0 (see rig.prune)."""
    if depsgraph.id_type_updated("WORLD") or depsgraph.id_type_updated("NODETREE"):
        try:
            rig.prune()
        except Exception as e:
            print("Open Sky: prune failed:", e)


@persistent
def _prune_before_render(*_args):
    """Scripts that set inputs and render in one go never reach the event
    loop that runs _prune_on_update. A render started from the UI runs in a
    job thread, where editing node links is unsafe (and not needed)."""
    if threading.current_thread() is threading.main_thread():
        try:
            rig.prune()
        except Exception as e:
            print("Open Sky: prune failed:", e)


def register():
    props.register()
    ops.register()
    ui.register()
    bpy.app.handlers.load_post.append(_upgrade_on_load)
    bpy.app.handlers.depsgraph_update_post.append(_prune_on_update)
    bpy.app.handlers.render_init.append(_prune_before_render)


def unregister():
    if _prune_before_render in bpy.app.handlers.render_init:
        bpy.app.handlers.render_init.remove(_prune_before_render)
    if _prune_on_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_prune_on_update)
    if _upgrade_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_upgrade_on_load)
    ui.unregister()
    ops.unregister()
    props.unregister()
