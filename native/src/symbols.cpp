#include "symbols.h"

#include <windows.h>
#include <dbghelp.h>

#include <string>

#include "log.h"

#pragma comment(lib, "dbghelp.lib")

namespace see {

//Any unique value works as the dbghelp "process" handle. Using our own keeps us out of the way
//of whatever Blender does with dbghelp for its crash reports.
static const HANDLE kFakeProcess = (HANDLE)(uintptr_t)0x5EE5EE;

static std::wstring pdb_name_from_image(HMODULE mod)
{
  auto *dos = (IMAGE_DOS_HEADER *)mod;
  auto *nt = (IMAGE_NT_HEADERS64 *)((uint8_t *)mod + dos->e_lfanew);
  auto &dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_DEBUG];
  if (!dir.VirtualAddress) {
    return L"";
  }
  auto *entries = (IMAGE_DEBUG_DIRECTORY *)((uint8_t *)mod + dir.VirtualAddress);
  size_t count = dir.Size / sizeof(IMAGE_DEBUG_DIRECTORY);
  for (size_t i = 0; i < count; i++) {
    if (entries[i].Type != IMAGE_DEBUG_TYPE_CODEVIEW) {
      continue;
    }
    const uint8_t *cv = (uint8_t *)mod + entries[i].AddressOfRawData;
    if (memcmp(cv, "RSDS", 4) != 0) {
      continue;
    }
    //CodeView record: "RSDS", GUID (16), age (4), then the PDB path
    const char *path = (const char *)(cv + 24);
    const char *slash = strrchr(path, '\\');
    const char *name = slash ? slash + 1 : path;
    return std::wstring(name, name + strlen(name));
  }
  return L"";
}

static BOOL CALLBACK dbg_callback(HANDLE, ULONG code, ULONG64 data, ULONG64)
{
  if (code == CBA_DEBUG_INFO) {
    std::string msg((const char *)data);
    while (!msg.empty() && (msg.back() == '\n' || msg.back() == '\r')) {
      msg.pop_back();
    }
    log("dbghelp: %s", msg.c_str());
  }
  return FALSE;
}

static bool file_exists(const std::wstring &p)
{
  return GetFileAttributesW(p.c_str()) != INVALID_FILE_ATTRIBUTES;
}

static uint64_t file_size(const std::wstring &p)
{
  WIN32_FILE_ATTRIBUTE_DATA d;
  if (!GetFileAttributesExW(p.c_str(), GetFileExInfoStandard, &d)) {
    return 0;
  }
  return ((uint64_t)d.nFileSizeHigh << 32) | d.nFileSizeLow;
}

bool Symbols::init()
{
  HMODULE exe = GetModuleHandleW(nullptr);
  wchar_t exe_path[MAX_PATH];
  GetModuleFileNameW(exe, exe_path, MAX_PATH);
  std::wstring exe_dir(exe_path);
  exe_dir = exe_dir.substr(0, exe_dir.find_last_of(L'\\'));

  std::wstring wanted = pdb_name_from_image(exe);
  std::wstring shipped = exe_dir + L"\\blender.pdb";
  log("exe: %ls, debug directory asks for: %ls", exe_path, wanted.c_str());

  std::wstring search = exe_dir;
  if (!wanted.empty() && !file_exists(exe_dir + L"\\" + wanted)) {
    if (!file_exists(shipped)) {
      log("no PDB found next to the executable (expected blender.pdb)");
      return false;
    }
    search = data_dir() + L"\\sym";
    CreateDirectoryW(search.c_str(), nullptr);
    std::wstring cached = search + L"\\" + wanted;
    if (file_size(cached) != file_size(shipped)) {
      log("copying symbols to %ls", cached.c_str());
      if (!CopyFileW(shipped.c_str(), cached.c_str(), FALSE)) {
        log("copy failed: %lu", GetLastError());
        return false;
      }
    }
  }

  //blender.pdb has public symbols only, so its signature differs from the one the exe asks for
  SymSetOptions(SYMOPT_FAIL_CRITICAL_ERRORS | SYMOPT_LOAD_ANYTHING | SYMOPT_DEBUG);
  if (!SymInitializeW(kFakeProcess, search.c_str(), FALSE)) {
    log("SymInitialize failed: %lu", GetLastError());
    return false;
  }
  SymRegisterCallback64(kFakeProcess, dbg_callback, 0);
  auto *nt = (IMAGE_NT_HEADERS64 *)((uint8_t *)exe + ((IMAGE_DOS_HEADER *)exe)->e_lfanew);
  base_ = SymLoadModuleExW(kFakeProcess, nullptr, exe_path, nullptr, (DWORD64)exe,
                           nt->OptionalHeader.SizeOfImage, nullptr, 0);
  process_ = kFakeProcess;
  if (!find("DNAstr")) {  //forces the deferred PDB load. Fails if only exports are available
    IMAGEHLP_MODULE64 mi = {sizeof(mi)};
    SymGetModuleInfo64(kFakeProcess, (DWORD64)exe, &mi);
    log("PDB not usable (symbol type %d, base %p, NumSyms %lu, loaded base %llx, last error %lu)",
        (int)mi.SymType, (void *)exe, mi.NumSyms, (unsigned long long)mi.BaseOfImage, GetLastError());
    process_ = nullptr;
    return false;
  }
  log("PDB loaded");
  return true;
}

struct FindCtx {
  const char *name;
  uint64_t address;
};

static BOOL CALLBACK find_cb(PSYMBOL_INFO si, ULONG, PVOID user)
{
  auto *ctx = (FindCtx *)user;
  bool match = strcmp(si->Name, ctx->name) == 0;
  if (!match) {
    char plain[512];
    if (UnDecorateSymbolName(si->Name, plain, sizeof(plain), UNDNAME_NAME_ONLY)) {
      match = strcmp(plain, ctx->name) == 0;
    }
  }
  if (match) {
    ctx->address = si->Address;
    return FALSE;
  }
  return TRUE;
}

//`name` is either a full decorated name or a plain one such as "DNAstr".
void *Symbols::find(const char *name) const
{
  if (!process_) {
    return nullptr;
  }
  //SymFromName does not find these names, so enumerate with a wildcard and compare
  std::string mask = std::string("*") + name + "*";
  FindCtx ctx = {name, 0};
  SymEnumSymbols(process_, (DWORD64)GetModuleHandleW(nullptr), mask.c_str(), find_cb, &ctx);
  return (void *)ctx.address;
}

void Symbols::shutdown()
{
  if (process_) {
    SymCleanup(process_);
    process_ = nullptr;
  }
}

}
