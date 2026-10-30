#pragma once
#include <cstdarg>
#include <cstdio>
#include <string>

namespace see {

//Appends to %LOCALAPPDATA%\NamedRerouteNode\see.log
void log_open();
void log(const char *fmt, ...);
std::wstring data_dir();

}
