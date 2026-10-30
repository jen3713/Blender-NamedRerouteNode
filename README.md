# Named Reroute Node

Named Reroute nodes for Blender's Shader, Geometry Nodes and Compositor editors. 

Blender 5.1+
Windows: full features. 
macOS/Linux: nodes, panel and link resolving work, but wires stay long, Use nodes are muted in the Shader Editor and the link-drag search is not extended.

## Build

1. Open `native/NamedRerouteNode.sln` in Visual Studio 2022 (C++ desktop workload).
2. Select **Release | x64** and build. `NamedRerouteNode.dll` is created next to `__init__.py`.

## Install

Copy this folder (the `native` folder is not needed) to
`%APPDATA%\Blender Foundation\Blender\5.1\scripts\addons\NamedRerouteNode`, then enable **Named Reroute Node** in
Preferences > Add-ons. `blender.pdb` must stay next to `blender.exe`.

## Use

- Add > Named Reroute, or drag a link on empty space and search "Named Reroute".
- Nodes with the same name share a color; the sidebar (N) > Node tab lists usages and jumps to the declaration.

Without the DLL the add-on still works, but the long wires stay visible and the "Use" nodes are muted.
