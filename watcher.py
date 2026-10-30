import traceback

import bpy

from . import native
from .constants import TREE_TYPES, is_decl, is_use
from .sync import links_changed, schedule, snapshot_links
from .trees import has_see_nodes, iter_trees

_signatures = {}


def _color_signature(tree):
    return hash(tuple(
        (n.name, n.rr_name, round(n.color[0], 3), round(n.color[1], 3), round(n.color[2], 3))
        for n in tree.nodes if is_decl(n) or is_use(n)
    ))


#moving or recoloring a node sends no update to its tree, so open editors are polled
def poll_colors():
    try:
        seen = set()
        for wm in bpy.data.window_managers:
            for win in wm.windows:
                for area in win.screen.areas:
                    if area.type != "NODE_EDITOR":
                        continue
                    sd = area.spaces.active
                    tree = getattr(sd, "edit_tree", None)
                    if sd.tree_type not in TREE_TYPES or tree is None:
                        continue
                    ptr = tree.as_pointer()
                    seen.add(ptr)
                    if has_see_nodes(tree):
                        if links_changed(tree):
                            schedule(tree)
                        else:
                            snapshot_links(tree)
                    sig = _color_signature(tree)
                    old = _signatures.get(ptr)
                    _signatures[ptr] = sig
                    if old is not None and old != sig:
                        schedule(tree)
        for ptr in list(_signatures):
            if ptr not in seen:
                del _signatures[ptr]
    except Exception:
        traceback.print_exc()
    return 0.25


#the DLL hooks in a moment after loading. Resync once it is active so existing links get flagged
def wait_for_hook():
    tries = wait_for_hook.tries = getattr(wait_for_hook, "tries", 0) + 1
    lib = native.dll()
    if lib is not None:
        native.set_enabled(True)
        for tree in iter_trees():
            if has_see_nodes(tree):
                schedule(tree)
        return None
    return 0.1 if tries < 600 else None


def register():
    bpy.app.timers.register(poll_colors, first_interval=1.0, persistent=True)
    wait_for_hook.tries = 0
    #a file opened at startup is loaded before the DLL hooks in, and loading drops non-persistent timers
    bpy.app.timers.register(wait_for_hook, first_interval=0.1, persistent=True)


def unregister():
    for fn in (poll_colors, wait_for_hook):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    _signatures.clear()
