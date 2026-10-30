#pragma once
#include <cstdint>

namespace see {

//Byte offsets of the DNA members the DLL touches, read from Blender's embedded DNA at startup.
struct Layout {
  int link_fromnode = -1, link_tonode = -1, link_fromsock = -1, link_tosock = -1;
  int link_flag = -1, link_sort_id = -1, link_size = -1, link_next = -1;
  int sock_next = -1, sock_identifier = -1, sock_in_out = -1;
  int node_next = -1, node_identifier = -1, node_idname = -1, node_outputs = -1, node_name = -1;
  int tree_nodes = -1, tree_links = -1;
  int space_edittree = -1;
};

extern Layout L;

template<typename T> T &at(void *base, int off)
{
  return *(T *)((uint8_t *)base + off);
}

}
