import bpy

from .constants import TREE_TYPES, is_decl, is_use
from .trees import find_input, load_targets, value_out


def _target_text(tree, usage):
    for node_name, socket_id in load_targets(usage):
        node = tree.nodes.get(node_name)
        sock = find_input(node, socket_id) if node else None
        if sock is not None:
            return f"{node.label or node.name} > {sock.name}"
    out = value_out(usage)
    if out is not None and out.links:
        link = out.links[0]
        return f"{link.to_node.label or link.to_node.name} > {link.to_socket.name}"
    return "not connected"


#top to bottom, then left to right, so the numbers follow the layout
def _usages(tree, name):
    found = [n for n in tree.nodes if is_use(n) and n.rr_name == name]
    found.sort(key=lambda n: (-round(n.location_absolute[1]), n.location_absolute[0]))
    return found


class SEE_PT_named_reroute(bpy.types.Panel):
    bl_idname = "SEE_PT_named_reroute"
    bl_label = "Named Reroute"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Node"

    @classmethod
    def poll(cls, context):
        sd = context.space_data
        node = context.active_node
        return (
            sd is not None
            and sd.type == "NODE_EDITOR"
            and sd.tree_type in TREE_TYPES
            and node is not None
            and (is_decl(node) or is_use(node))
        )

    def draw(self, context):
        layout = self.layout
        tree = context.space_data.edit_tree
        node = context.active_node
        name = node.rr_name
        decl = next((n for n in tree.nodes if is_decl(n) and n.rr_name == name), None)

        row = layout.row()
        row.enabled = decl is not None
        op = row.operator("see.goto_node", text="Go to Declaration", icon="VIEWZOOM")
        op.node_name = decl.name if decl else ""

        usages = _usages(tree, name)
        box = layout.box()
        box.label(text=f"Usages ({len(usages)})")
        if not usages:
            box.label(text="No usages")
        col = box.column(align=True)
        for index, usage in enumerate(usages, 1):
            op = col.operator("see.goto_node", text=f"{index}. {_target_text(tree, usage)}")
            op.node_name = usage.name


classes = (SEE_PT_named_reroute,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
