//NamedRerouteNode: makes Named Reroute links look like short wires in the regular Shader Editor.
//
//The material keeps real source->target links, so every render engine keeps working. The Python
//add-on flags those links (see_mark_link) and remembers which Usage node each belongs to. While the
//editor draws a flagged link, this DLL swaps in a temporary link that starts at the Usage node.

#include <windows.h>

#include <cstring>
#include <unordered_map>

#include "hook.h"
#include "layout.h"
#include "linkdrag.h"
#include "log.h"
#include "sdna.h"
#include "symbols.h"

namespace {

using see::at;
using see::L;

constexpr int kLinkFlag = 1 << 24;   //unused bit of bNodeLink::flag. Saved with the .blend
constexpr int kMultiFlag = 1 << 25;  //the sort id orders the links of a multi input socket, so the Usage node is kept in g_multi
//Usage node identifier of the flagged links that end in a multi input socket. Empty after loading until the add-on flags them again
std::unordered_map<void *, int> g_multi;
constexpr const char *kUsageIdname = "SEE_NamedRerouteUsage";
constexpr const char *kGpuNodesSymbol = "?ntreeGPUMaterialNodes@blender@@YAXPEAUbNodeTree@1@PEAUGPUMaterial@1@@Z";
constexpr const char *kRemoveLinkSymbol = "?node_remove_link@bke@blender@@YAXPEAUbNodeTree@2@AEAUbNodeLink@2@@Z";
constexpr const char *kDrawSocketSymbol = "blender::ed::space_node::node_draw_socket";
constexpr const char *kDrawSocketsSymbol = "blender::ed::space_node::node_draw_sockets";
constexpr const char *kDrawLinkDraggedSymbol =
    "?node_draw_link_dragged@space_node@ed@blender@@YAXAEBUbContext@3@AEBUView2D@3@AEBUSpaceNode@3@AEBUbNodeLink@3@@Z";
constexpr const char *kDrawLinkSymbol =
    "?node_draw_link@space_node@ed@blender@@YAXAEBUbContext@3@AEBUView2D@3@AEBUSpaceNode@3@AEBUbNodeLink@3@_N@Z";

volatile LONG g_status = 0;  //bit 0 draw hook, bit 1 EEVEE protection, bit 2 link drag popup
volatile LONG g_drawn = 0;   //links redirected so far (diagnostics)
using RemoveLinkFn = void (*)(void *tree, void *link);
RemoveLinkFn g_remove_link = nullptr;
volatile LONG g_enabled = 1;  //the add-on switches the redirect off while it is disabled

//Called on entry of node_draw_link(bContext &, View2D &, SpaceNode &snode, bNodeLink &link, bool).
bool on_draw_link(CONTEXT *ctx)
{
  if (!g_enabled) {
    return false;
  }
  void *snode = (void *)ctx->R8;
  void *link = (void *)ctx->R9;
  int flag = at<int>(link, L.link_flag);
  if (!(flag & kLinkFlag)) {
    return false;
  }
  void *tree = at<void *>(snode, L.space_edittree);
  if (!tree) {
    return false;
  }
  int id = at<int>(link, L.link_sort_id);
  if (flag & kMultiFlag) {
    auto it = g_multi.find(link);
    if (it == g_multi.end()) {
      return false;
    }
    id = it->second;
  }
  void *node = at<void *>(tree, L.tree_nodes);  //ListBase::first
  for (; node; node = at<void *>(node, L.node_next)) {
    if (at<int>(node, L.node_identifier) == id &&
        strncmp((const char *)node + L.node_idname, kUsageIdname, strlen(kUsageIdname)) == 0) {
      break;
    }
  }
  if (!node) {
    return false;  //Usage node is gone: draw the real wire
  }
  //The Usage node has a decorative "Name" output above the real "Value" one.
  void *out = at<void *>(node, L.node_outputs);  //ListBase::first
  while (out && strncmp((const char *)out + L.sock_identifier, "Value", 64) != 0) {
    out = at<void *>(out, L.sock_next);
  }
  if (!out) {
    return false;
  }
  //a copy is drawn instead, so the real link stays untouched
  static thread_local uint8_t copy[512];
  memcpy(copy, link, L.link_size);
  at<void *>(copy, L.link_fromnode) = node;
  at<void *>(copy, L.link_fromsock) = out;
  at<int>(copy, L.link_flag) = flag & ~kLinkFlag;
  ctx->R9 = (DWORD64)copy;
  InterlockedIncrement(&g_drawn);
  return false;
}


//Called on entry of ntreeGPUMaterialNodes(bNodeTree *local_copy, GPUMaterial *).
//EEVEE compiles a temporary copy of the material tree. A Usage node (a Python node without a GPU
//implementation) feeding a shader input crashes ntree_shader_weight_tree_invert, and such a link exists
//for a moment before the add-on replaces it with the real one. Drop those links from the copy only.
bool on_gpu_material_nodes(CONTEXT *ctx)
{
  if (!g_enabled || !g_remove_link) {
    return false;
  }
  void *tree = (void *)ctx->Rcx;
  if (!tree) {
    return false;
  }
  void *link = at<void *>(tree, L.tree_links);  //ListBase::first
  while (link) {
    void *next = at<void *>(link, L.link_next);
    void *from = at<void *>(link, L.link_fromnode);
    if (from && strncmp((const char *)from + L.node_idname, kUsageIdname, strlen(kUsageIdname)) == 0) {
      g_remove_link(tree, link);
    }
    link = next;
  }
  return false;
}


//---- hiding the decorative "Name" socket of Usage nodes
//A Usage node draws its name dropdown inside the row of a transparent first output so that it appears above
//"Value". Blender still outlines that socket's dot, so the per-socket draw call is skipped for it.
//The argument lists of the two (static) draw functions are not in the symbols, so the arguments are scanned
//for a bNode / bNodeSocket instead of relying on their order.

void *g_draw_socket = nullptr;

bool read_matches(void *p, int off, const char *text, bool prefix)
{
  __try {
    return strncmp((const char *)p + off, text, prefix ? strlen(text) : 64) == 0;
  }
  __except (EXCEPTION_EXECUTE_HANDLER) {
    return false;
  }
}

template<typename Fn> bool any_arg(const CONTEXT *ctx, Fn match)
{
  uint64_t args[10] = {ctx->Rcx, ctx->Rdx, ctx->R8, ctx->R9};
  const uint64_t *stack = (const uint64_t *)ctx->Rsp;
  for (int i = 0; i < 6; i++) {
    args[4 + i] = stack[5 + i];  //[rsp+0x28 ...]: stack arguments after the shadow space
  }
  for (uint64_t a : args) {
    if (a > 0x10000 && match((void *)a)) {
      return true;
    }
  }
  return false;
}

//node_draw_sockets(..., node, ...): runs once per node. Arm the per-socket hook only for Usage nodes.
bool on_draw_sockets(CONTEXT *ctx)
{
  if (!g_enabled || !g_draw_socket) {
    return false;
  }
  bool usage = any_arg(ctx, [](void *p) { return read_matches(p, L.node_idname, kUsageIdname, true); });
  see::hook_arm(g_draw_socket, usage);
  return false;
}

bool on_draw_socket(CONTEXT *ctx)
{
  if (!g_enabled) {
    return false;
  }
  return any_arg(ctx, [](void *p) { return read_matches(p, L.sock_identifier, "Name", false); });
}

bool resolve_layout(const see::Symbols &sym)
{
  auto *dna = (const uint8_t *)sym.find("DNAstr");
  auto *dna_len = (const int *)sym.find("DNAlen");
  if (!dna || !dna_len) {
    see::log("DNAstr/DNAlen not found");
    return false;
  }
  see::Sdna sdna;
  if (!sdna.parse(dna, (size_t)*dna_len)) {
    see::log("could not parse DNA");
    return false;
  }
  see::log("bNodeLink = %s", sdna.describe("bNodeLink").c_str());
  L.link_fromnode = sdna.offset("bNodeLink", "fromnode");
  L.link_tonode = sdna.offset("bNodeLink", "tonode");
  L.link_fromsock = sdna.offset("bNodeLink", "fromsock");
  L.link_tosock = sdna.offset("bNodeLink", "tosock");
  L.link_flag = sdna.offset("bNodeLink", "flag");
  L.link_sort_id = sdna.offset("bNodeLink", "multi_input_socket_index");
  L.link_size = sdna.size("bNodeLink");
  L.node_next = sdna.offset("bNode", "next");
  L.node_identifier = sdna.offset("bNode", "identifier");
  L.node_idname = sdna.offset("bNode", "idname");
  L.node_outputs = sdna.offset("bNode", "outputs");
  L.node_name = sdna.offset("bNode", "name");
  L.sock_in_out = sdna.offset("bNodeSocket", "in_out");
  L.sock_next = sdna.offset("bNodeSocket", "next");
  L.sock_identifier = sdna.offset("bNodeSocket", "identifier");
  L.tree_nodes = sdna.offset("bNodeTree", "nodes");
  L.tree_links = sdna.offset("bNodeTree", "links");
  L.link_next = sdna.offset("bNodeLink", "next");
  L.space_edittree = sdna.offset("SpaceNode", "edittree");
  see::log("bNodeLink: from %d/%d to %d/%d flag %d sort_id %d size %d", L.link_fromnode,
           L.link_fromsock, L.link_tonode, L.link_tosock, L.link_flag, L.link_sort_id, L.link_size);
  see::log("bNode: next %d identifier %d idname %d outputs %d; bNodeTree.nodes %d; SpaceNode.edittree %d",
           L.node_next, L.node_identifier, L.node_idname, L.node_outputs, L.tree_nodes,
           L.space_edittree);
  const int all[] = {L.link_fromnode, L.link_tonode, L.link_fromsock, L.link_tosock, L.link_flag,
                     L.link_sort_id, L.link_size, L.node_next, L.node_identifier, L.node_idname,
                     L.node_outputs, L.tree_nodes, L.space_edittree, L.tree_links, L.link_next, L.sock_next, L.sock_identifier, L.node_name, L.sock_in_out};
  for (int v : all) {
    if (v < 0) {
      see::log("a DNA member is missing: this Blender version is not supported");
      return false;
    }
  }
  return L.link_size <= 512;
}

DWORD WINAPI init_thread(LPVOID)
{
  //symbols, DNA offsets and every function must resolve before anything is patched
  see::log_open();
  see::log("NamedRerouteNode loading");
  see::Symbols sym;
  if (!sym.init()) {
    see::log("symbols unavailable, nothing hooked");
    return 0;
  }
  void *draw_link = sym.find(kDrawLinkSymbol);
  void *draw_dragged = sym.find(kDrawLinkDraggedSymbol);
  void *gpu_nodes = sym.find(kGpuNodesSymbol);
  void *remove_link = sym.find(kRemoveLinkSymbol);
  void *draw_socket = sym.find(kDrawSocketSymbol);
  void *draw_sockets = sym.find(kDrawSocketsSymbol);
  bool layout_ok = resolve_layout(sym);
  bool link_drag = layout_ok && see::linkdrag::install(sym);
  sym.shutdown();
  if (!draw_link || !layout_ok) {
    see::log("node_draw_link %p, layout %d: nothing hooked", draw_link, (int)layout_ok);
    return 0;
  }
  see::log("node_draw_link at %p", draw_link);
  if (see::hook_install(draw_link, on_draw_link)) {
    InterlockedOr(&g_status, 1);
    see::log("draw hook installed");
    //a link picked up from an input socket is a copy of the flagged one and is drawn by this function while dragging
    if (draw_dragged && see::hook_install(draw_dragged, on_draw_link)) {
      see::log("dragged link hook installed");
    }
  }
  if (link_drag) {
    InterlockedOr(&g_status, 4);
    see::log("link drag search extended");
  }
  g_remove_link = (RemoveLinkFn)remove_link;
  if (draw_socket && draw_sockets) {
    g_draw_socket = draw_socket;
    bool ok1 = see::hook_install(draw_socket, on_draw_socket, /*armed=*/false);
    bool ok2 = see::hook_install(draw_sockets, on_draw_sockets);
    see::log("socket hooks: %d %d (draw_socket %p, draw_sockets %p)", (int)ok1, (int)ok2, draw_socket,
             draw_sockets);
  }
  if (gpu_nodes && remove_link && see::hook_install(gpu_nodes, on_gpu_material_nodes)) {
    InterlockedOr(&g_status, 2);
    see::log("EEVEE protection hook installed (ntreeGPUMaterialNodes at %p)", gpu_nodes);
  }
  return 0;
}

}

extern "C" {

__declspec(dllexport) int see_version()
{
  return 4;
}

//bit 0: link drawing hook is active, bit 1: EEVEE compile protection is active
__declspec(dllexport) int see_status()
{
  return (int)g_status;
}

__declspec(dllexport) void see_set_enabled(int on)
{
  g_enabled = on ? 1 : 0;
}

__declspec(dllexport) int see_redirected_count()
{
  return (int)g_drawn;
}

//Flags `link` (bNodeLink *) so the editor draws it as starting at `usage_node` (bNode *).
__declspec(dllexport) int see_mark_link(void *link, void *usage_node, int multi)
{
  if (!(g_status & 1) || !link || !usage_node) {
    return -1;
  }
  __try {
    int id = at<int>(usage_node, L.node_identifier);
    if (multi) {
      g_multi[link] = id;
      at<int>(link, L.link_flag) |= kLinkFlag | kMultiFlag;
    }
    else {
      g_multi.erase(link);
      at<int>(link, L.link_sort_id) = id;
      at<int>(link, L.link_flag) = (at<int>(link, L.link_flag) | kLinkFlag) & ~kMultiFlag;
    }
  }
  __except (EXCEPTION_EXECUTE_HANDLER) {
    return -2;
  }
  return 0;
}

__declspec(dllexport) int see_unmark_link(void *link)
{
  if (!(g_status & 1) || !link) {
    return -1;
  }
  __try {
    at<int>(link, L.link_flag) &= ~(kLinkFlag | kMultiFlag);
    g_multi.erase(link);
  }
  __except (EXCEPTION_EXECUTE_HANDLER) {
    return -2;
  }
  return 0;
}

}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(module);
    //Loader lock is held here, so do the real work on another thread.
    HANDLE t = CreateThread(nullptr, 0, init_thread, nullptr, 0, nullptr);
    if (t) {
      CloseHandle(t);
    }
  }
  else if (reason == DLL_PROCESS_DETACH) {
    //Keep the hook handler alive until process exit. Removing it here could race a draw call.
  }
  return TRUE;
}
