#pragma once
#include <cstdint>
#include <string>

namespace see {

//Resolves addresses of Blender functions/data from the public symbols of blender.pdb
//(shipped next to blender.exe). The PDB is copied once to %LOCALAPPDATA%\NamedRerouteNode\sym
//under the file name the executable's debug directory asks for.
class Symbols {
 public:
  bool init();
  void *find(const char *name) const;
  void shutdown();

 private:
  void *process_ = nullptr;
  uint64_t base_ = 0;
};

}
