#include "sdna.h"

#include <cstring>

namespace see {

//every block of the DNA string is padded to 4 bytes
static const uint8_t *align4(const uint8_t *p, const uint8_t *begin)
{
  size_t off = (size_t)(p - begin);
  return begin + ((off + 3) & ~(size_t)3);
}

bool Sdna::parse(const uint8_t *data, size_t len)
{
  const uint8_t *begin = data, *end = data + len, *p = data;
  auto expect = [&](const char *tag) {
    if (p + 4 > end || memcmp(p, tag, 4) != 0) {
      return false;
    }
    p += 4;
    return true;
  };
  auto read_i32 = [&]() {
    int32_t v;
    memcpy(&v, p, 4);
    p += 4;
    return v;
  };
  auto read_i16 = [&]() {
    int16_t v;
    memcpy(&v, p, 2);
    p += 2;
    return v;
  };

  if (!expect("SDNA") || !expect("NAME")) {
    return false;
  }
  int32_t n = read_i32();
  for (int i = 0; i < n; i++) {
    names_.emplace_back((const char *)p);
    p += names_.back().size() + 1;
  }
  p = align4(p, begin);
  if (!expect("TYPE")) {
    return false;
  }
  n = read_i32();
  for (int i = 0; i < n; i++) {
    types_.emplace_back((const char *)p);
    p += types_.back().size() + 1;
  }
  p = align4(p, begin);
  if (!expect("TLEN")) {
    return false;
  }
  for (size_t i = 0; i < types_.size(); i++) {
    lengths_.push_back(read_i16());
  }
  p = align4(p, begin);
  if (!expect("STRC")) {
    return false;
  }
  n = read_i32();
  for (int i = 0; i < n; i++) {
    Struct s;
    s.type = read_i16();
    int16_t count = read_i16();
    for (int j = 0; j < count; j++) {
      int16_t t = read_i16();
      int16_t nm = read_i16();
      s.members.emplace_back(t, nm);
    }
    structs_.push_back(std::move(s));
  }
  return !structs_.empty();
}

const Sdna::Struct *Sdna::find_struct(const char *name) const
{
  for (const Struct &s : structs_) {
    if (types_[s.type] == name) {
      return &s;
    }
  }
  return nullptr;
}

int Sdna::member_size(const std::pair<int16_t, int16_t> &m) const
{
  const std::string &nm = names_[m.second];
  int base;
  //pointers and function pointers are 8 bytes, arrays multiply the size
  if (nm[0] == '*' || nm.compare(0, 2, "(*") == 0) {
    base = 8;
  }
  else {
    base = lengths_[m.first];
  }
  size_t pos = nm.find('[');
  while (pos != std::string::npos) {
    base *= atoi(nm.c_str() + pos + 1);
    pos = nm.find('[', pos + 1);
  }
  return base;
}

static std::string base_name(const std::string &nm)
{
  size_t i = 0;
  while (i < nm.size() && (nm[i] == '*' || nm[i] == '(')) {
    i++;
  }
  size_t j = i;
  while (j < nm.size() && nm[j] != '[' && nm[j] != ')' && nm[j] != '(') {
    j++;
  }
  return nm.substr(i, j - i);
}

int Sdna::offset(const char *struct_name, const char *member) const
{
  const Struct *s = find_struct(struct_name);
  if (!s) {
    return -1;
  }
  int off = 0;
  for (const auto &m : s->members) {
    if (base_name(names_[m.second]) == member) {
      return off;
    }
    off += member_size(m);
  }
  return -1;
}

int Sdna::size(const char *struct_name) const
{
  const Struct *s = find_struct(struct_name);
  return s ? lengths_[s->type] : -1;
}

std::string Sdna::describe(const char *struct_name) const
{
  const Struct *s = find_struct(struct_name);
  if (!s) {
    return "(no such struct)";
  }
  std::string out;
  int off = 0;
  for (const auto &m : s->members) {
    out += std::to_string(off) + " " + types_[m.first] + " " + names_[m.second] + "; ";
    off += member_size(m);
  }
  return out;
}

}
