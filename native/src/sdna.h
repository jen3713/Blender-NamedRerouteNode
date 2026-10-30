#pragma once
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace see {

//Minimal reader for Blender's embedded DNA description (the DNAstr blob), so struct member
//offsets are read from the running Blender instead of being hard-coded.
class Sdna {
 public:
  bool parse(const uint8_t *data, size_t len);
  //Byte offset of `member` inside `struct_name`, or -1.
  int offset(const char *struct_name, const char *member) const;
  //Size of the struct in bytes, or -1.
  int size(const char *struct_name) const;
  //"offset type name" per member, for diagnostics.
  std::string describe(const char *struct_name) const;

 private:
  struct Struct {
    int type;
    std::vector<std::pair<int16_t, int16_t>> members;  //(type index, name index)
  };
  const Struct *find_struct(const char *name) const;
  int member_size(const std::pair<int16_t, int16_t> &m) const;

  std::vector<std::string> names_, types_;
  std::vector<int16_t> lengths_;
  std::vector<Struct> structs_;
};

}
