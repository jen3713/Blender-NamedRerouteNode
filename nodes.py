import bpy
from bpy.props import BoolProperty, FloatVectorProperty, StringProperty

from . import native
from .colors import default_color
from .constants import LABEL, TREE_TYPES, decl_idname, is_use, use_idname
from .sync import keep_inserted_source, resolve_early, schedule, wants_mute


def _on_name(self, context):
    schedule(self.id_data)


class _SEENode:
    rr_name: StringProperty(name="Name", update=_on_name)
    rr_applied: FloatVectorProperty(size=3, subtype="COLOR", min=0.0, max=1.0)
    rr_colored: BoolProperty()
    rr_color_name: StringProperty()

    def update(self):
        #a Python node cannot be evaluated, so its links are resolved before anything runs
        if is_use(self):
            keep_inserted_source(self.id_data, self)
            resolve_early(self.id_data, self)
        schedule(self.id_data)


#node buttons are always drawn below the outputs, so the name dropdown lives in the row of a transparent first output
class SEE_SocketName(bpy.types.NodeSocket):
    bl_idname = "SEE_SocketName"
    bl_label = "Name"

    def draw(self, context, layout, node, text):
        layout.alignment = "EXPAND"
        op = layout.operator_menu_enum(
            "see.pick_name", "name", text=node.rr_name or "Select..."
        )
        op.node_name = node.name

    def draw_color(self, context, node):
        return (0.0, 0.0, 0.0, 0.0)

    @classmethod
    def draw_color_simple(cls):
        return (0.0, 0.0, 0.0, 0.0)


def _decl_init(self, context):
    s = self.inputs.new("NodeSocketColor", "Value")
    s.hide_value = True
    self.label = LABEL
    self.use_custom_color = True
    self.color = default_color("")


def _decl_draw_buttons(self, context, layout):
    layout.prop(self, "rr_name", text="")


def _use_init(self, context):
    self.outputs.new("SEE_SocketName", "Name")
    self.outputs.new("NodeSocketColor", "Value")
    self.label = LABEL
    self.use_custom_color = True
    self.color = default_color("")
    #see sync.sync_tree: unprotected trees keep Usage nodes muted
    self.mute = wants_mute(self.id_data, self)


#one Declare/Use pair per tree type. Every class needs its own bl_idname and base class
def _make_node_classes(tree_type):
    base_name, suffix = TREE_TYPES[tree_type]
    base = getattr(bpy.types, base_name)

    def poll(cls, ntree):
        return ntree.bl_idname == tree_type

    decl = type("SEE_NT_Declaration" + suffix, (_SEENode, base), {
        "bl_idname": decl_idname(tree_type),
        "bl_label": LABEL,
        "bl_width_default": 170,
        "poll": classmethod(poll),
        "init": _decl_init,
        "draw_buttons": _decl_draw_buttons,
        "__annotations__": {"rr_prev": StringProperty()},
    })
    use = type("SEE_NT_Usage" + suffix, (_SEENode, base), {
        "bl_idname": use_idname(tree_type),
        "bl_label": LABEL,
        "bl_width_default": 170,
        "poll": classmethod(poll),
        "init": _use_init,
        "__annotations__": {"rr_targets": StringProperty(), "rr_src": StringProperty()},
    })
    return decl, use


node_classes = []
for _tree_type in TREE_TYPES:
    node_classes.extend(_make_node_classes(_tree_type))

classes = (SEE_SocketName, *node_classes)


def register():
    for tree_type in TREE_TYPES:
        setattr(getattr(bpy.types, tree_type), "see_virtual", BoolProperty(name="Compact Wires", default=False))
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    for tree_type in TREE_TYPES:
        delattr(getattr(bpy.types, tree_type), "see_virtual")
