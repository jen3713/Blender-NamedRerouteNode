import bpy
from bpy.app.handlers import persistent

from . import native
from .sync import resolve, schedule, virtualize
from .trees import has_see_nodes, iter_trees


#without the DLL the compact short links are not evaluable, so they are resolved while rendering or saving
@persistent
def _resolve_for_output(*args):
    if native.dll() is not None:
        return
    for tree in iter_trees():
        if tree.see_virtual and has_see_nodes(tree):
            resolve(tree)


@persistent
def _after_output(*args):
    if native.dll() is not None:
        return
    for tree in iter_trees():
        if tree.see_virtual and has_see_nodes(tree):
            virtualize(tree)


@persistent
def _on_load(*args):
    _after_output()
    for tree in iter_trees():
        if has_see_nodes(tree):
            schedule(tree)


_handlers = (
    ("render_pre", _resolve_for_output),
    ("render_post", _after_output),
    ("render_cancel", _after_output),
    ("save_pre", _resolve_for_output),
    ("save_post", _after_output),
    ("load_post", _on_load),
)


def register():
    for name, fn in _handlers:
        getattr(bpy.app.handlers, name).append(fn)


def unregister():
    for name, fn in _handlers:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
