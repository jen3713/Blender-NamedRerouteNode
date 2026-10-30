#pragma once
#include <windows.h>

namespace see {

//Entry-point breakpoint hook. The first byte of the target is replaced with INT3. The handler
//may edit the register context (arguments) and the original instruction then runs unmodified
//via a single step. No instruction relocation, so it works on any function prologue.
//A hook function returns true to skip the call: the function then returns at once (void functions only).
using HookFn = bool (*)(CONTEXT *ctx);

bool hook_install(void *target, HookFn pre, bool armed = true);
//A disarmed hook costs nothing. Arm it only while its calls matter.
void hook_arm(void *target, bool armed);
void hook_remove_all();

}
