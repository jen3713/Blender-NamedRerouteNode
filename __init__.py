bl_info = {
    "name": "Named Reroute Node",
    "author": "Jen_",
    "version": (1, 3, 0),
    "blender": (5, 1, 0),
    "location": "Node Editor > Add > Named Reroute",
    "description": "Named Reroute nodes for the Shader, Geometry Nodes and Compositor editors",
    "category": "Node",
}

from . import (
    colors,
    constants,
    handlers,
    linkdrag,
    native,
    nodes,
    operators,
    panels,
    preferences,
    sync,
    trees,
    ui,
    watcher,
)

_modules = (preferences, native, nodes, operators, panels, ui, handlers, watcher)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
