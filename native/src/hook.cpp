#include "hook.h"

#include <vector>

#include "log.h"

namespace see {

struct Hook {
  uint8_t *addr;
  uint8_t orig;
  HookFn pre;
  bool armed;
};

static std::vector<Hook> g_hooks;
static PVOID g_veh = nullptr;
//hook whose original instruction is being single-stepped on this thread
static thread_local Hook *t_pending = nullptr;

static void write_byte(uint8_t *addr, uint8_t value)
{
  DWORD old;
  VirtualProtect(addr, 1, PAGE_EXECUTE_READWRITE, &old);
  *addr = value;
  VirtualProtect(addr, 1, old, &old);
  FlushInstructionCache(GetCurrentProcess(), addr, 1);
}

static LONG CALLBACK handler(EXCEPTION_POINTERS *ep)
{
  EXCEPTION_RECORD *er = ep->ExceptionRecord;
  CONTEXT *ctx = ep->ContextRecord;

  if (er->ExceptionCode == EXCEPTION_BREAKPOINT) {
    for (Hook &h : g_hooks) {
      //Rip may point past the INT3, so match on ExceptionAddress
      if ((uint8_t *)er->ExceptionAddress != h.addr) {
        continue;
      }
      ctx->Rip = (DWORD64)h.addr;  //re-run the real first instruction
      bool skip = false;
      __try {
        skip = h.pre(ctx);
      }
      __except (EXCEPTION_EXECUTE_HANDLER) {
        //A bad pointer in a hook must never take Blender down. Just run the original code.
      }
      if (skip) {
        ctx->Rip = *(uint64_t *)ctx->Rsp;  //behave like `ret`
        ctx->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
      }
      write_byte(h.addr, h.orig);
      ctx->EFlags |= 0x100;  //trap flag: stop again after the original instruction
      t_pending = &h;
      return EXCEPTION_CONTINUE_EXECUTION;
    }
    return EXCEPTION_CONTINUE_SEARCH;
  }

  if (er->ExceptionCode == EXCEPTION_SINGLE_STEP && t_pending) {
    if (t_pending->armed) {
      write_byte(t_pending->addr, 0xCC);
    }
    t_pending = nullptr;
    return EXCEPTION_CONTINUE_EXECUTION;
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

bool hook_install(void *target, HookFn pre, bool armed)
{
  if (!g_veh) {
    g_veh = AddVectoredExceptionHandler(1, handler);
  }
  g_hooks.reserve(16);  //handler holds pointers into the vector
  Hook h = {(uint8_t *)target, *(uint8_t *)target, pre, armed};
  if (h.orig == 0xCC) {
    log("hook target %p already starts with INT3", target);
    return false;
  }
  g_hooks.push_back(h);
  if (armed) {
    write_byte(h.addr, 0xCC);
  }
  return true;
}

void hook_arm(void *target, bool armed)
{
  for (Hook &h : g_hooks) {
    if (h.addr == (uint8_t *)target && h.armed != armed) {
      h.armed = armed;
      write_byte(h.addr, armed ? 0xCC : h.orig);
    }
  }
}

void hook_remove_all()
{
  for (Hook &h : g_hooks) {
    write_byte(h.addr, h.orig);
  }
  g_hooks.clear();
  if (g_veh) {
    RemoveVectoredExceptionHandler(g_veh);
    g_veh = nullptr;
  }
}

}
