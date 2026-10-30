#include "log.h"

#include <windows.h>
#include <shlobj.h>

namespace see {

static FILE *g_log = nullptr;

std::wstring data_dir()
{
  wchar_t buf[MAX_PATH];
  DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", buf, MAX_PATH);
  std::wstring dir = n ? std::wstring(buf, n) : L"C:\\";
  dir += L"\\NamedRerouteNode";
  CreateDirectoryW(dir.c_str(), nullptr);
  return dir;
}

void log_open()
{
  if (g_log) {
    return;
  }
  std::wstring path = data_dir() + L"\\see.log";
  g_log = _wfopen(path.c_str(), L"w");
}

void log(const char *fmt, ...)
{
  if (!g_log) {
    return;
  }
  SYSTEMTIME t;
  GetLocalTime(&t);
  fprintf(g_log, "[%02d:%02d:%02d.%03d] ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
  va_list ap;
  va_start(ap, fmt);
  vfprintf(g_log, fmt, ap);
  va_end(ap);
  fputc('\n', g_log);
  fflush(g_log);
}

}
