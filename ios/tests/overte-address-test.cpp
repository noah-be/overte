// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "OverteAddress.h"

#include <cassert>

using overte::ios::AddressKind;
using overte::ios::parseOverteAddress;

int main() {
    auto place = parseOverteAddress(" overte_hub ");
    assert(place.kind == AddressKind::Place);
    assert(place.host == "overte_hub");
    assert(place.port == 40102);
    assert(place.normalized == "hifi://overte_hub");

    auto domain = parseOverteAddress("HIFI://Example.COM:40114/1,2,3");
    assert(domain.kind == AddressKind::Network);
    assert(domain.host == "example.com");
    assert(domain.port == 40114);
    assert(domain.explicitPort);
    assert(domain.path == "/1,2,3");
    assert(domain.normalized == "hifi://example.com:40114/1,2,3");

    auto ipv6 = parseOverteAddress("hifi://[2001:db8::1]:40102/");
    assert(ipv6.kind == AddressKind::Network);
    assert(ipv6.host == "2001:db8::1");
    assert(ipv6.normalized == "hifi://[2001:db8::1]:40102/");

    assert(!parseOverteAddress(""));
    assert(!parseOverteAddress("https://example.com"));
    assert(!parseOverteAddress("hifi://example.com:0"));
    assert(!parseOverteAddress("hifi://example.com:70000"));
    assert(!parseOverteAddress("hifi://@someone"));
    assert(!parseOverteAddress("bad place"));
    return 0;
}
