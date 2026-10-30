import colorsys
import hashlib

from .preferences import addon_prefs


def default_color(name):
    p = addon_prefs()
    if not name or (p is not None and not p.hash_colors):
        return tuple(p.default_color) if p else (0.16, 0.32, 0.45)
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return colorsys.hsv_to_rgb(h, 0.55, 0.5)


def _differs(a, b):
    return any(abs(x - y) > 1e-3 for x, y in zip(a, b))


def sync_colors(nodes):
    #nodes with one name share a color: a node whose color moved away from the applied one was recolored by the user
    groups = {}
    for n in nodes:
        groups.setdefault(n.rr_name, []).append(n)
    for name, ns in groups.items():
        known = [n for n in ns if n.rr_colored and n.rr_color_name == name]
        changed = [n for n in known if _differs(n.color, n.rr_applied)]
        if changed:
            target = tuple(changed[0].color)
        elif known:
            target = tuple(known[0].rr_applied)
        else:
            target = default_color(name)
        for n in ns:
            if not n.use_custom_color:
                n.use_custom_color = True
            if _differs(n.color, target):
                n.color = target
            if _differs(n.rr_applied, target):
                n.rr_applied = target
            n.rr_colored = True
            n.rr_color_name = name
