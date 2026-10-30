import bpy
from bpy.props import BoolProperty, FloatVectorProperty


#None while the add-on is only being enabled
def addon_prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


class SEEPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    default_color: FloatVectorProperty(
        name="Named Reroute color", subtype="COLOR", size=3, min=0.0, max=1.0, default=(0.16, 0.32, 0.45)
    )
    hash_colors: BoolProperty(
        name="Unique color per name",
        description="Give every new Named Reroute name its own color instead of the color above",
        default=True,
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "default_color")
        col.prop(self, "hash_colors")


classes = (SEEPreferences,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
