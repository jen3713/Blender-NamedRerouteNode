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
