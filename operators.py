import bpy
from bpy.props import EnumProperty, StringProperty

from .constants import TREE_TYPES, is_decl
from .sync import resolve, sync_tree, virtualize
from .trees import has_see_nodes, iter_trees

#the enum items callback needs its strings kept alive
_items_cache = []


def _name_items(self, context):
    global _items_cache
    tree = getattr(context.space_data, "edit_tree", None)
    names = []
    if tree:
        names = sorted({n.rr_name for n in tree.nodes if is_decl(n) and n.rr_name})
    _items_cache = [(n, n, "") for n in names] or [("", "No declarations", "")]
    return _items_cache


class SEE_OT_pick_name(bpy.types.Operator):
    bl_idname = "see.pick_name"
    bl_label = "Pick Named Reroute"
    bl_options = {"UNDO", "INTERNAL"}

    node_name: StringProperty()
    name: EnumProperty(items=_name_items)

    def execute(self, context):
        tree = context.space_data.edit_tree
        node = tree.nodes.get(self.node_name) if tree else None
        if node is None or not self.name:
            return {"CANCELLED"}
        node.rr_name = self.name
        return {"FINISHED"}


class SEE_OT_toggle_virtual(bpy.types.Operator):
    bl_idname = "see.toggle_virtual"
    bl_label = "Compact Wires"
    bl_description = (
        "Without the DLL: show short Usage->target links for editing. The tree is incomplete "
        "until switched off (resolved automatically on render and save)"
    )
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        sd = context.space_data
        return sd and sd.type == "NODE_EDITOR" and sd.tree_type in TREE_TYPES and sd.edit_tree

    def execute(self, context):
        tree = context.space_data.edit_tree
        tree.see_virtual = not tree.see_virtual
        sync_tree(tree)
        if tree.see_virtual:
            virtualize(tree)
        else:
            resolve(tree)
        return {"FINISHED"}


class SEE_OT_remark(bpy.types.Operator):
    bl_idname = "see.remark_links"
    bl_label = "Refresh Named Reroute Wires"
    bl_description = "Re-flag all Named Reroute links so the DLL draws them as short wires"

    def execute(self, context):
        n = 0
        for tree in iter_trees():
            if has_see_nodes(tree):
                sync_tree(tree)
                n += 1
        self.report({"INFO"}, f"Refreshed {n} node trees")
        return {"FINISHED"}


class SEE_OT_goto_node(bpy.types.Operator):
    bl_idname = "see.goto_node"
    bl_label = "Go to Node"
    bl_description = "Select the node and focus the graph on it"
    bl_options = {"INTERNAL"}

    node_name: StringProperty()

    @classmethod
    def poll(cls, context):
        sd = context.space_data
        return sd and sd.type == "NODE_EDITOR" and sd.edit_tree is not None

    def execute(self, context):
        tree = context.space_data.edit_tree
        node = tree.nodes.get(self.node_name)
        if node is None:
            return {"CANCELLED"}
        for n in tree.nodes:
            n.select = False
        node.select = True
        tree.nodes.active = node
        #only an invoked operator animates the view, like Numpad Period, and it needs the main region rather than the sidebar
        region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        if region is None:
            bpy.ops.node.view_selected()
            return {"FINISHED"}
        with context.temp_override(region=region):
            bpy.ops.node.view_selected("INVOKE_DEFAULT")
        return {"FINISHED"}


classes = (SEE_OT_pick_name, SEE_OT_toggle_virtual, SEE_OT_remark, SEE_OT_goto_node)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
