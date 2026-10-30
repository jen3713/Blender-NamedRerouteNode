TREE_TYPES = {
    "ShaderNodeTree": ("ShaderNode", ""),
    "GeometryNodeTree": ("GeometryNode", "_Geometry"),
    "CompositorNodeTree": ("CompositorNode", "_Compositor"),
}
#the DLL matches Usage nodes by this idname prefix. Each tree type adds its own suffix
DECL_PREFIX = "SEE_NamedRerouteDeclaration"
USE_PREFIX = "SEE_NamedRerouteUsage"
LABEL = "Named Reroute"
DLL_NAME = "NamedRerouteNode.dll"

SOCKET_FOR_TYPE = {
    "VALUE": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "BOOLEAN": "NodeSocketBool",
    "VECTOR": "NodeSocketVector",
    "RGBA": "NodeSocketColor",
    "SHADER": "NodeSocketShader",
    "GEOMETRY": "NodeSocketGeometry",
    "STRING": "NodeSocketString",
    "OBJECT": "NodeSocketObject",
    "COLLECTION": "NodeSocketCollection",
    "MATERIAL": "NodeSocketMaterial",
    "IMAGE": "NodeSocketImage",
    "TEXTURE": "NodeSocketTexture",
    "ROTATION": "NodeSocketRotation",
    "MATRIX": "NodeSocketMatrix",
}


def is_decl(node):
    return node.bl_idname.startswith(DECL_PREFIX)


def is_use(node):
    return node.bl_idname.startswith(USE_PREFIX)


def decl_idname(tree_type):
    return DECL_PREFIX + TREE_TYPES[tree_type][1]


def use_idname(tree_type):
    return USE_PREFIX + TREE_TYPES[tree_type][1]
