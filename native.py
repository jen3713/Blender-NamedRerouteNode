import ctypes
import os
import traceback

from .constants import DLL_NAME

_dll = None
_load_tried = False


def _dll_path():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DLL_NAME)
    return path if os.path.isfile(path) else None


def _loaded_handle():
    k32 = ctypes.windll.kernel32
    k32.GetModuleHandleW.restype = ctypes.c_void_p
    return k32.GetModuleHandleW(DLL_NAME)


def load_dll():
    global _load_tried
    if _loaded_handle() or _load_tried or os.name != "nt":
        return
    _load_tried = True
    path = _dll_path()
    if path:
        try:
            ctypes.WinDLL(path)
        except OSError:
            traceback.print_exc()


def dll():
    #the DLL installs its hooks a moment after loading, so a loaded DLL is not yet an active one
    global _dll
    if _dll is not None:
        return _dll
    if os.name != "nt" or not _loaded_handle():
        return None
    lib = ctypes.WinDLL(DLL_NAME)
    lib.see_status.restype = ctypes.c_int
    lib.see_mark_link.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.see_unmark_link.argtypes = [ctypes.c_void_p]
    lib.see_set_enabled.argtypes = [ctypes.c_int]
    if not (lib.see_status() & 1):
        return None
    _dll = lib
    return _dll


def set_enabled(on):
    if _dll is not None:
        _dll.see_set_enabled(1 if on else 0)


def usage_protected(tree):
    #True when a Usage node can stay unmuted without crashing the engine of this tree type
    if tree.bl_idname == "GeometryNodeTree":
        return True
    if tree.bl_idname == "CompositorNodeTree":
        #the compositor calls a null function for Python nodes and cannot be hooked. Usage links are replaced early, see sync.wants_mute
        return False
    lib = dll()
    #bit 1: the DLL strips Usage links from the copy EEVEE compiles
    return lib is not None and bool(lib.see_status() & 2)


def mark_links(usage, target_socket, src):
    #a multi input socket can hold other links too, only the one from the declaration source is drawn from the Usage node
    lib = dll()
    if lib is None:
        return
    multi = 1 if target_socket.is_multi_input else 0
    for link in target_socket.links:
        if link.from_node == usage:
            continue
        if link.from_socket == src:
            lib.see_mark_link(link.as_pointer(), usage.as_pointer(), multi)
        else:
            lib.see_unmark_link(link.as_pointer())


def unmark_link(link):
    lib = dll()
    if lib is not None:
        lib.see_unmark_link(link.as_pointer())


def register():
    load_dll()


def unregister():
    set_enabled(False)
