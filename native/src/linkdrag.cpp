//Named Reroute entries in the popup that opens when a link is dropped on empty space.
//
//That popup is built in C++ from node declarations, which Python nodes do not have, so the entries are
//added by hand: the update callback of the popup runs the original and then appends our items, and the
//exec callback handles a chosen item by asking the add-on's linkdrag module to create the node.
//The add-on passes its package name with see_set_python_package: it differs between an add-on and an extension install.
//Every call into Python goes through PyRun_SimpleString. The add-on talks back through the see_* exports.

#include "linkdrag.h"

#include <windows.h>

#include <cctype>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include "hook.h"
#include "layout.h"
#include "log.h"
#include "symbols.h"

namespace see {
namespace linkdrag {
namespace {

struct StringRef {
  const char *data;
  int64_t size;
};

using SearchItemAddFn = bool (*)(void *items, StringRef name, void *data, int icon, int64_t flag, unsigned char extra);
using UpdateFn = void (*)(const void *C, void *storage, const char *query, void *items, bool is_first);
using GilEnsureFn = int (*)();
using GilReleaseFn = void (*)(int);
using RunSimpleFn = int (*)(const char *);

struct Item {
  int kind;
  std::string label;
  std::string name;
};

struct Drag {
  std::string node;
  std::string socket;
  bool is_output = false;
};

std::vector<std::unique_ptr<Item>> g_items;
Drag g_drag;
void *g_update = nullptr;
void *g_exec = nullptr;
void *g_invoke = nullptr;
SearchItemAddFn g_add = nullptr;
GilEnsureFn g_gil_ensure = nullptr;
GilReleaseFn g_gil_release = nullptr;
RunSimpleFn g_run = nullptr;
std::string g_package;

bool resolve_python()
{
  for (const wchar_t *name : {L"python313.dll", L"python312.dll", L"python311.dll", L"python3.dll"}) {
    HMODULE py = GetModuleHandleW(name);
    if (!py) {
      continue;
    }
    g_gil_ensure = (GilEnsureFn)GetProcAddress(py, "PyGILState_Ensure");
    g_gil_release = (GilReleaseFn)GetProcAddress(py, "PyGILState_Release");
    g_run = (RunSimpleFn)GetProcAddress(py, "PyRun_SimpleString");
    if (g_gil_ensure && g_gil_release && g_run) {
      return true;
    }
  }
  log("link drag: Python C API not found");
  return false;
}

//calls a function of the add-on's linkdrag module
void run_python(const std::string &call)
{
  if (g_package.empty()) {
    log("link drag: Python package not set");
    return;
  }
  std::string code = "import " + g_package + ".linkdrag as _l; _l." + call;
  int state = g_gil_ensure();
  g_run(code.c_str());
  g_gil_release(state);
}

//every space separated word of the query has to be part of the label
bool matches(const char *query, const std::string &label)
{
  if (!query || !*query) {
    return true;
  }
  std::string hay = label;
  for (char &c : hay) {
    c = (char)tolower((unsigned char)c);
  }
  std::string token;
  for (const char *p = query;; p++) {
    if (*p && *p != ' ') {
      token += (char)tolower((unsigned char)*p);
      continue;
    }
    if (!token.empty() && hay.find(token) == std::string::npos) {
      return false;
    }
    token.clear();
    if (!*p) {
      break;
    }
  }
  return true;
}

int safe_add(void *items, Item *item, DWORD *code)
{
  __try {
    return g_add(items, StringRef{item->label.c_str(), (int64_t)item->label.size()}, item, 0, 0, 0) ? 1 : 0;
  }
  __except (*code = GetExceptionCode(), EXCEPTION_EXECUTE_HANDLER) {
    return -1;
  }
}

bool on_invoke(CONTEXT *ctx)
{
  void *node = (void *)ctx->Rdx;
  void *socket = (void *)ctx->R8;
  g_drag.node = (const char *)node + L.node_name;
  g_drag.socket = (const char *)socket + L.sock_identifier;
  g_drag.is_output = (at<uint8_t>(socket, L.sock_in_out) & 2) != 0;
  return false;
}

bool on_update(CONTEXT *ctx)
{
  void *C = (void *)ctx->Rcx;
  void *storage = (void *)ctx->Rdx;
  const char *query = (const char *)ctx->R8;
  void *items = (void *)ctx->R9;
  //fifth argument: on the stack after the return address and the 32-byte shadow space
  bool is_first = *(uint8_t *)(ctx->Rsp + 0x28) != 0;

  if (is_first) {
    g_items.clear();
    run_python("prepare()");
  }

  auto add_ours = [&]() {
    int added = 0;
    for (auto &item : g_items) {
      if (matches(query, item->label)) {
        DWORD code = 0;
        int r = safe_add(items, item.get(), &code);
        if (r < 0) {
          log("link drag: search_item_add raised %08lx", code);
        }
        added += r > 0 ? 1 : 0;
      }
    }
    return added;
  };
  //search_item_add fails once the list is full and the original fills it, so ours go first for a typed query
  const bool typed = query && *query && *query != ' ';
  int added = 0;
  if (typed) {
    added = add_ours();
  }

  //call the original: disarm the breakpoint for the call, then arm it again
  hook_arm(g_update, false);
  ((UpdateFn)g_update)(C, storage, query, items, is_first);
  hook_arm(g_update, true);

  if (!typed) {
    added = add_ours();
  }
  return true;
}

bool on_exec(CONTEXT *ctx)
{
  void *chosen = (void *)ctx->R8;
  for (size_t i = 0; i < g_items.size(); i++) {
    if (g_items[i].get() == chosen) {
      run_python("apply(" + std::to_string(i) + ")");
      return true;
    }
  }
  return false;
}

}

bool install(const Symbols &sym)
{
  g_update = sym.find("blender::ed::space_node::link_drag_search_update_fn");
  g_exec = sym.find("blender::ed::space_node::link_drag_search_exec_fn");
  g_invoke = sym.find(
      "?invoke_node_link_drag_add_menu@space_node@ed@blender@@YAXAEAUbContext@3@AEAUbNode@3@AEAUbNodeSocket@3@AEBU?$VecBase@M$01@3@@Z");
  //the flag argument is an int up to Blender 5.1 and an int64 after it. Passing it as int64 is safe for both
  g_add = (SearchItemAddFn)sym.find("?search_item_add@ui@blender@@YA_NPEAUSearchItems@12@VStringRef@2@PEAXHHE@Z");
  if (!g_add) {
    g_add = (SearchItemAddFn)sym.find("?search_item_add@ui@blender@@YA_NPEAUSearchItems@12@VStringRef@2@PEAXH_JE@Z");
  }
  log("link drag: update %p, exec %p, invoke %p, search_item_add %p", g_update, g_exec, g_invoke, (void *)g_add);
  if (!g_update || !g_exec || !g_invoke || !g_add || !resolve_python()) {
    return false;
  }
  bool ok = hook_install(g_invoke, on_invoke);
  ok = hook_install(g_update, on_update) && ok;
  ok = hook_install(g_exec, on_exec) && ok;
  return ok;
}

}
}

extern "C" {

__declspec(dllexport) void see_set_python_package(const char *package)
{
  see::linkdrag::g_package = package ? package : "";
}

__declspec(dllexport) void see_clear_link_items()
{
  see::linkdrag::g_items.clear();
}

__declspec(dllexport) void see_add_link_item(int kind, const char *label, const char *name)
{
  using namespace see::linkdrag;
  auto item = std::make_unique<Item>();
  item->kind = kind;
  item->label = label;
  item->name = name;
  g_items.push_back(std::move(item));
}

__declspec(dllexport) int see_link_item_kind(int index)
{
  using namespace see::linkdrag;
  return index >= 0 && index < (int)g_items.size() ? g_items[index]->kind : -1;
}

__declspec(dllexport) const char *see_link_item_name(int index)
{
  using namespace see::linkdrag;
  return index >= 0 && index < (int)g_items.size() ? g_items[index]->name.c_str() : "";
}

__declspec(dllexport) const char *see_drag_node()
{
  return see::linkdrag::g_drag.node.c_str();
}

__declspec(dllexport) const char *see_drag_socket()
{
  return see::linkdrag::g_drag.socket.c_str();
}

__declspec(dllexport) int see_drag_is_output()
{
  return see::linkdrag::g_drag.is_output ? 1 : 0;
}

}
