import bpy

from . import native
from .constants import TREE_TYPES, decl_idname, is_decl, use_idname


def _add_menu_items(layout, context):
    tree_type = context.space_data.tree_type
    op = layout.operator("node.add_node", text="Named Reroute Node")
    op.type = decl_idname(tree_type)
    op.use_transform = True
    tree = getattr(context.space_data, "edit_tree", None)
    names = sorted({n.rr_name for n in tree.nodes if is_decl(n) and n.rr_name}) if tree else []
    if names:
        layout.separator()
    for name in names:
        op = layout.operator("node.add_node", text=name)
        op.type = use_idname(tree_type)
        op.use_transform = True
        item = op.settings.add()
        item.name = "rr_name"
        item.value = repr(name)


class SEE_MT_add(bpy.types.Menu):
    bl_idname = "SEE_MT_add"
    bl_label = "Named Reroute"

    def draw(self, context):
        _add_menu_items(self.layout, context)


def _add_menu(self, context):
    if context.space_data.tree_type in TREE_TYPES:
        self.layout.separator()
        self.layout.menu(SEE_MT_add.bl_idname)


def _header(self, context):
    sd = context.space_data
    if sd.tree_type in TREE_TYPES and sd.edit_tree and native.dll() is None:
        self.layout.operator("see.toggle_virtual", text="Compact Wires", depress=sd.edit_tree.see_virtual)


def register():
    bpy.utils.register_class(SEE_MT_add)
    bpy.types.NODE_MT_add.append(_add_menu)
    bpy.types.NODE_HT_header.append(_header)


def unregister():
    bpy.types.NODE_HT_header.remove(_header)
    bpy.types.NODE_MT_add.remove(_add_menu)
    bpy.utils.unregister_class(SEE_MT_add)
