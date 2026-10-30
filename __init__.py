if "bpy" in locals():
    import importlib

    #dependencies first, so every module reloads against already reloaded imports
    importlib.reload(constants)
    importlib.reload(preferences)
    importlib.reload(trees)
    importlib.reload(native)
    importlib.reload(colors)
    importlib.reload(sync)
    importlib.reload(nodes)
    importlib.reload(linkdrag)
    importlib.reload(operators)
    importlib.reload(panels)
    importlib.reload(ui)
    importlib.reload(handlers)
    importlib.reload(watcher)
else:
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

import bpy  # noqa: F401

_modules = (preferences, native, nodes, operators, panels, ui, handlers, watcher)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
