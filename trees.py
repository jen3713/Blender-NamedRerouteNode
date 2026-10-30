import json

import bpy

from .constants import TREE_TYPES, is_decl, is_use


def iter_trees():
    #the compositing group is also a node group, so the same tree can show up twice
    seen = set()
    candidates = []
    for coll in (bpy.data.materials, bpy.data.worlds, bpy.data.lights):
        for idb in coll:
            if idb.node_tree:
                candidates.append(idb.node_tree)
    candidates.extend(g for g in bpy.data.node_groups if g.bl_idname in TREE_TYPES)
    for sc in bpy.data.scenes:
        group = getattr(sc, "compositing_node_group", None)
        if group is not None and group.bl_idname == "CompositorNodeTree":
            candidates.append(group)
    for tree in candidates:
        ptr = tree.as_pointer()
        if ptr not in seen:
            seen.add(ptr)
            yield tree


def has_see_nodes(tree):
    return any(is_decl(n) or is_use(n) for n in tree.nodes)


def redraw_node_editors():
    for wm in bpy.data.window_managers:
        for win in wm.windows:
            for area in win.screen.areas:
                if area.type == "NODE_EDITOR":
                    area.tag_redraw()


#a Usage node has a decorative "Name" output first. "Value" is the real one
def value_out(usage):
    return next((s for s in usage.outputs if s.identifier == "Value"), None)


def find_input(node, identifier):
    return next((s for s in node.inputs if s.identifier == identifier), None)


def find_output(node, identifier):
    return next((s for s in node.outputs if s.identifier == identifier), None)


def sock_ref(sock):
    return f"{sock.node.name}|{sock.identifier}"


def load_targets(usage):
    try:
        return [tuple(t) for t in json.loads(usage.rr_targets or "[]")]
    except ValueError:
        return []


def save_targets(usage, targets):
    usage.rr_targets = json.dumps(targets)


def source_socket(tree, name):
    if not name:
        return None
    for n in tree.nodes:
        if is_decl(n) and n.rr_name == name:
            links = n.inputs[0].links
            if links and not links[0].is_muted:
                return links[0].from_socket
    return None
