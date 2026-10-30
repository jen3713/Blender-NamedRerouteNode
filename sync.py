import traceback

import bpy

from . import native
from .colors import sync_colors
from .constants import SOCKET_FOR_TYPE, LABEL, decl_idname, is_decl, is_use
from .trees import (
    find_input,
    find_output,
    iter_trees,
    load_targets,
    redraw_node_editors,
    save_targets,
    sock_ref,
    source_socket,
    value_out,
)


def _socket_idname(sock_type):
    idname = SOCKET_FOR_TYPE.get(sock_type)
    return idname if idname and hasattr(bpy.types, idname) else None


def _retype_decl(tree, node):
    links = node.inputs[0].links
    if not links:
        return
    src = links[0].from_socket
    idname = _socket_idname(src.type)
    if idname and node.inputs[0].bl_idname != idname:
        try:
            node.inputs.remove(node.inputs[0])
            new = node.inputs.new(idname, "Value")
        except (TypeError, RuntimeError):
            new = node.inputs.new("NodeSocketColor", "Value")
        new.hide_value = True
        tree.links.new(src, new)


def _retype_usage(tree, node, src):
    idname = _socket_idname(src.type)
    old = value_out(node)
    if not idname or old is None or old.bl_idname == idname:
        return
    targets = [(l.to_node, l.to_socket.identifier) for l in old.links]
    node.outputs.remove(old)
    try:
        new = node.outputs.new(idname, "Value")
    except (TypeError, RuntimeError):
        new = node.outputs.new("NodeSocketColor", "Value")
    for tn, sid in targets:
        ts = find_input(tn, sid)
        if ts:
            tree.links.new(new, ts)


def _unique_names(decls, usages):
    seen = set()
    for d in decls:
        want = d.rr_name or "Reroute"
        name, i = want, 0
        while name in seen:
            i += 1
            name = f"{want}.{i:03d}"
        others = {x.rr_name for x in decls if x is not d}
        if d.rr_prev and d.rr_prev != name and d.rr_prev not in others:
            for u in usages:
                if u.rr_name == d.rr_prev:
                    u.rr_name = name
                    u.rr_color_name = name
            d.rr_color_name = name
        if d.rr_name != name:
            d.rr_name = name
        d.rr_prev = name
        seen.add(name)


def _our_link(ts, usage, src):
    #a multi input socket holds several links, the Usage one is the one from its node or from the declaration source
    for link in ts.links:
        if link.from_node == usage or link.from_socket == src:
            return link
    for link in ts.links:
        if src is not None and _same_group_output(link, src):
            return link
    return ts.links[0]


def _same_group_output(link, src):
    #making a group gives every crossing link its own output socket on the group node, all carrying the same value
    return link.from_node == src.node and "NodeGroup" in src.node.bl_idname and link.from_socket != src


def _forget_replaced(tree, usage):
    #without a source nothing owns the real links. A target the user wired to something else by hand is no longer fed by this node
    keep = []
    for nn, sid in load_targets(usage):
        tn = tree.nodes.get(nn)
        ts = find_input(tn, sid) if tn else None
        if ts is not None and ts.links:
            link = _our_link(ts, usage, None)
            if link.from_node != usage and sock_ref(link.from_socket) != usage.rr_src:
                continue
        keep.append([nn, sid])
    if keep != [list(t) for t in load_targets(usage)]:
        save_targets(usage, keep)


def _propagate(tree, usage, claimed):
    #keeps the real links in step with the declaration. A link from some other source was set by the user
    src = source_socket(tree, usage.rr_name)
    if src is None:
        _forget_replaced(tree, usage)
        return
    keep = []
    for nn, sid in load_targets(usage):
        tn = tree.nodes.get(nn)
        ts = find_input(tn, sid) if tn else None
        if ts is None or not ts.links:
            continue
        #a duplicated Usage node inherits the targets of the original, which keeps them
        if (nn, sid) in claimed:
            continue
        link = _our_link(ts, usage, src)
        if link.from_node == usage or link.from_socket == src:
            keep.append([nn, sid])
        elif sock_ref(link.from_socket) == usage.rr_src or _same_group_output(link, src):
            tree.links.remove(link)
            tree.links.new(src, ts)
            keep.append([nn, sid])
        else:
            continue
        claimed.add((nn, sid))
        native.mark_links(usage, ts, src)
    save_targets(usage, keep)
    usage.rr_src = sock_ref(src)


def _link_or_drop(tree, src, ts):
    #validity of a fresh link is only known after the tree update, see _drop_invalid
    tree.links.new(src, ts)
    return True


def _drop_invalid(tree, usages):
    #a link between incompatible sockets is invalid and would disable the whole tree, so it is discarded
    for u in usages:
        src = source_socket(tree, u.rr_name)
        if src is None:
            continue
        keep = []
        for nn, sid in load_targets(u):
            tn = tree.nodes.get(nn)
            ts = find_input(tn, sid) if tn else None
            link = _our_link(ts, u, src) if ts is not None and ts.links else None
            if link is not None and link.from_socket == src and not link.is_valid:
                tree.links.remove(link)
                continue
            keep.append([nn, sid])
        save_targets(u, keep)


def _take_target(tree, usage, rec):
    #a link made from this Usage node moves the target over from any other Usage node that fed it before
    rec = tuple(rec)
    for other in tree.nodes:
        if other == usage or not is_use(other):
            continue
        targets = load_targets(other)
        if rec in targets:
            targets.remove(rec)
            save_targets(other, targets)
    targets = load_targets(usage)
    if rec not in targets:
        targets.append(rec)
    save_targets(usage, targets)


def resolve(tree):
    #Python nodes cannot be evaluated, so Usage->target becomes source->target. The DLL draws it from the Usage node
    for link in list(tree.links):
        u = link.from_node
        if not is_use(u):
            continue
        src = source_socket(tree, u.rr_name)
        if src is None:
            continue
        tn, ts = link.to_node, link.to_socket
        tree.links.remove(link)
        if not _link_or_drop(tree, src, ts):
            continue
        native.mark_links(u, ts, src)
        _take_target(tree, u, [tn.name, ts.identifier])
        u.rr_src = sock_ref(src)


#a Usage node dropped on a wire takes the place of its source (Blender re-uses the link), so the links of every tree are remembered
_snapshots = {}


def _link_map(tree):
    return {l.as_pointer(): (sock_ref(l.from_socket), sock_ref(l.to_socket)) for l in tree.links}


def snapshot_links(tree):
    _snapshots[tree.as_pointer()] = _link_map(tree)


def links_changed(tree):
    snap = _snapshots.get(tree.as_pointer())
    return snap is not None and snap != _link_map(tree)


def fix_node_inserts(tree, usages):
    #a node dropped on a wire re-uses the link: it now starts at the new node, but keeps the flag that draws it from the Usage
    #node, while the link that feeds the new node starts at the old source. The Usage node feeds the new node instead
    snap = _snapshots.get(tree.as_pointer())
    if not snap:
        return
    fresh = [l for l in tree.links if l.as_pointer() not in snap]
    for link in tree.links:
        old = snap.get(link.as_pointer())
        if old is None or old[0] == sock_ref(link.from_socket) or old[1] != sock_ref(link.to_socket):
            continue
        if is_use(link.from_node):
            continue
        native.unmark_link(link)
        owners = [u for u in usages if [link.to_node.name, link.to_socket.identifier] in [list(t) for t in load_targets(u)]]
        for u in owners:
            targets = [list(t) for t in load_targets(u)]
            targets.remove([link.to_node.name, link.to_socket.identifier])
            save_targets(u, targets)
            for new in fresh:
                if sock_ref(new.from_socket) == old[0]:
                    _take_target(tree, u, [new.to_node.name, new.to_socket.identifier])


def keep_inserted_source(tree, usage):
    #the wire it was dropped on keeps its source, and the Usage node is connected to the first free input of that source
    snap = _snapshots.get(tree.as_pointer())
    out = value_out(usage)
    if not snap or out is None:
        return
    for link in list(out.links):
        old = snap.get(link.as_pointer())
        if old is None or old[1] != sock_ref(link.to_socket):
            continue
        node_name, _, ident = old[0].partition("|")
        node = tree.nodes.get(node_name)
        if node is None or node == usage or is_use(node):
            continue
        from_sock = find_output(node, ident)
        if from_sock is None:
            continue
        ts = link.to_socket
        tree.links.remove(link)
        tree.links.new(from_sock, ts)
        free = [i for i in node.inputs if not i.links and not i.is_unavailable and not i.hide]
        pick = next((i for i in free if i.type == out.type), free[0] if free else None)
        if pick is not None:
            tree.links.new(out, pick)


def wants_mute(tree, usage):
    #the compositor cannot run a Python node, so a Usage node without a source to replace its links with stays bypassed
    if tree.bl_idname == "CompositorNodeTree":
        return source_socket(tree, usage.rr_name) is None
    return not native.usage_protected(tree)


def resolve_early(tree, usage):
    #runs while the tree updates, before anything evaluates it. Gizmo nodes walk back through their input links and cannot
    #handle a Python node on the way, and the compositor cannot run one at all
    compositor = tree.bl_idname == "CompositorNodeTree"
    if (tree.bl_idname != "GeometryNodeTree" and not compositor) or tree.see_virtual:
        return
    out = value_out(usage)
    if out is None or not out.links:
        return
    src = source_socket(tree, usage.rr_name)
    if compositor and src is None and not usage.mute:
        usage.mute = True
    for link in list(out.links):
        #the validity of a link that leaves a Python node is not reliable, only the resolved link says
        if src is None or not (compositor or "Gizmo" in link.to_node.bl_idname):
            continue
        tn, ts = link.to_node, link.to_socket
        tree.links.remove(link)
        if not _link_or_drop(tree, src, ts):
            continue
        native.mark_links(usage, ts, src)
        _take_target(tree, usage, [tn.name, ts.identifier])
        usage.rr_src = sock_ref(src)


def virtualize(tree):
    #fallback without the DLL: put the short Usage->target links back
    for u in [n for n in tree.nodes if is_use(n)]:
        src = source_socket(tree, u.rr_name)
        if src is None:
            continue
        for nn, sid in load_targets(u):
            tn = tree.nodes.get(nn)
            ts = find_input(tn, sid) if tn else None
            if ts and ts.links and ts.links[0].from_socket == src:
                tree.links.remove(ts.links[0])
                tree.links.new(value_out(u), ts)


def _ensure_name_socket(tree, usage):
    #older nodes lack the decorative first output. Nothing may be wired to it
    name = next((s for s in usage.outputs if s.identifier == "Name"), None)
    if name is None:
        name = usage.outputs.new("SEE_SocketName", "Name")
        try:
            usage.outputs.move(len(usage.outputs) - 1, 0)
        except (AttributeError, TypeError, RuntimeError):
            pass
    for link in list(name.links):
        tree.links.remove(link)


def _adopt_orphans(tree, decls, usages):
    #grouping nodes (Ctrl+G) moves Usage nodes away from their declaration. What fed their targets before arrives through a
    #Group Input socket now, so a declaration for that socket is created next to them
    declared = {d.rr_name for d in decls}
    orphans = {}
    for u in usages:
        if u.rr_name and u.rr_name not in declared:
            orphans.setdefault(u.rr_name, []).append(u)
    for name, group in orphans.items():
        sources = set()
        for u in group:
            for nn, sid in load_targets(u):
                tn = tree.nodes.get(nn)
                ts = find_input(tn, sid) if tn else None
                for link in ts.links if ts else ():
                    if link.from_node.bl_idname == "NodeGroupInput":
                        sources.add(link.from_socket)
        if len(sources) != 1:
            continue
        src = sources.pop()
        first = group[0]
        decl = tree.nodes.new(decl_idname(tree.bl_idname))
        decl.rr_name = name
        decl.rr_prev = name
        decl.location = (first.location.x - 220, first.location.y)
        tree.links.new(src, decl.inputs[0])
        decls.append(decl)


def sync_tree(tree):
    decls = [n for n in tree.nodes if is_decl(n)]
    usages = [n for n in tree.nodes if is_use(n)]
    if not decls and not usages:
        return
    fix_node_inserts(tree, usages)
    _adopt_orphans(tree, decls, usages)
    _unique_names(decls, usages)
    for d in decls:
        _retype_decl(tree, d)
    for u in usages:
        src = source_socket(tree, u.rr_name)
        if src is not None:
            _retype_usage(tree, u, src)
    for n in decls + usages:
        if not n.label:
            n.label = LABEL
    for u in usages:
        _ensure_name_socket(tree, u)
    sync_colors(decls + usages)
    #a muted node is bypassed by every engine, which keeps the transient Usage link from crashing it
    for u in usages:
        want_mute = wants_mute(tree, u)
        if u.mute != want_mute:
            u.mute = want_mute
    if not tree.see_virtual or native.dll() is not None:
        claimed = set()
        for u in usages:
            _propagate(tree, u, claimed)
        resolve(tree)
        _drop_invalid(tree, usages)
    snapshot_links(tree)


_dirty = set()


def schedule(tree):
    #timers are dropped on file load unless persistent, so ask Blender instead of keeping a flag
    _dirty.add(tree.as_pointer())
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.02, persistent=True)


def _tick():
    ptrs = set(_dirty)
    _dirty.clear()
    for tree in iter_trees():
        if tree.as_pointer() in ptrs:
            try:
                sync_tree(tree)
            except Exception:
                traceback.print_exc()
    redraw_node_editors()
    return None
