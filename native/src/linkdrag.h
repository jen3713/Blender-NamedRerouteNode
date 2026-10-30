#pragma once

namespace see {

class Symbols;

//Adds Named Reroute entries to the search popup that opens when a link is dropped on empty space.
namespace linkdrag {

//Resolves the symbols and installs the hooks. Returns true when the popup is extended.
bool install(const Symbols &sym);

}
}
