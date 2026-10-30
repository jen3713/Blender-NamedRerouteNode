import ctypes

import bpy

from . import native
from .constants import TREE_TYPES, decl_idname, is_decl, use_idname
from .trees import value_out

KIND_DECLARE = 0
KIND_USE = 1


def _lib():
    lib = native.dll()
    if lib is None:
        return None
    if not getattr(lib, "_see_link_drag", False):
        lib.see_add_link_item.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
        lib.see_link_item_kind.argtypes = [ctypes.c_int]
        lib.see_link_item_name.argtypes = [ctypes.c_int]
        lib.see_link_item_name.restype = ctypes.c_char_p
        lib.see_drag_node.restype = ctypes.c_char_p
        lib.see_drag_socket.restype = ctypes.c_char_p
        lib.see_drag_is_output.restype = ctypes.c_int
        lib._see_link_drag = True
    return lib


#the callbacks come from the DLL while the popup is open. The bpy.context still points at the node editor
def _edit_tree():
    sd = getattr(bpy.context, "space_data", None)
    if sd is None or getattr(sd, "type", "") != "NODE_EDITOR" or sd.tree_type not in TREE_TYPES:
        return None
    return sd.edit_tree


#called by the DLL when the popup opens: an output can start a Declare, an input can take a Use of a known name
def prepare():
    lib = _lib()
    if lib is None:
        return
    lib.see_clear_link_items()
    tree = _edit_tree()
    if tree is None:
        return
    if lib.see_drag_is_output():
        lib.see_add_link_item(KIND_DECLARE, b"Named Reroute", b"")
        return
    names = sorted({n.rr_name for n in tree.nodes if is_decl(n) and n.rr_name})
    for name in names:
        lib.see_add_link_item(KIND_USE, f"Named Reroute > {name}".encode("utf-8"), name.encode("utf-8"))


#called by the DLL when one of our items is chosen
def apply(index):
    lib = _lib()
    tree = _edit_tree()
    if lib is None or tree is None:
        return
    kind = lib.see_link_item_kind(index)
    name = (lib.see_link_item_name(index) or b"").decode("utf-8")
    source = tree.nodes.get((lib.see_drag_node() or b"").decode("utf-8"))
    socket_id = (lib.see_drag_socket() or b"").decode("utf-8")
    if source is None or kind < 0:
        return
    sd = bpy.context.space_data
    for n in tree.nodes:
        n.select = False
    if kind == KIND_DECLARE:
        from_socket = next((s for s in source.outputs if s.identifier == socket_id), None)
        node = tree.nodes.new(decl_idname(tree.bl_idname))
        node.location = _spot(sd)
        if from_socket is not None:
            tree.links.new(from_socket, node.inputs[0])
    else:
        to_socket = next((s for s in source.inputs if s.identifier == socket_id), None)
        node = tree.nodes.new(use_idname(tree.bl_idname))
        node.rr_name = name
        node.location = _spot(sd)
        if to_socket is not None:
            tree.links.new(value_out(node), to_socket)
    node.select = True
    tree.nodes.active = node


def _spot(space):
    x, y = space.cursor_location
    return (x - 90.0, y + 30.0)
