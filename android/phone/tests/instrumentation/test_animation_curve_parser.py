#!/usr/bin/env python3
"""Run the production recursive FBX node parser on synthetic binary trees.

Qt is unavailable on the host. Minimal byte-stream/container adapters replace Qt;
the recursive parser itself is extracted unchanged. The property decoder is a
single-integer fixture adapter: compressed property decoding is not tested here.
"""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[4]
source = (repo / 'libraries/model-serializers/src/FBXSerializer_Node.cpp').read_text()
start = source.index('FBXNode parseBinaryFBXNode(')
end = source.index('\nclass Tokenizer', start)
parser = source[start:end]

fixture = r'''
#include <cassert>
#include <cstdint>
#include <limits>
#include <string>
#include <type_traits>
#include <vector>
using qint64 = int64_t;
using quint64 = uint64_t;
using qint32 = int32_t;
using quint32 = uint32_t;
using quint8 = uint8_t;
struct Bytes {
    std::string value;
    bool null = true;
    Bytes() = default;
    Bytes(std::string text) : value(text), null(false) {}
    bool isNull() const { return null; }
    bool operator==(const char* text) const { return value == text; }
};
template<class T> struct List : std::vector<T> {
    void append(const T& item) { this->push_back(item); }
};
struct FBXNode { Bytes name; List<int32_t> properties; List<FBXNode> children; };
struct Device {
    std::vector<uint8_t> data;
    size_t cursor = 27;
    bool sequential = false, seekWorks = true;
    int successfulSeeks = 0;
    bool isSequential() const { return sequential; }
    int64_t size() const { return data.size(); }
    bool seek(int64_t offset) {
        if (!seekWorks) return false;
        assert(offset >= 0 && offset <= size());
        cursor = offset; ++successfulSeeks; return true;
    }
    Bytes read(size_t length) {
        assert(cursor + length <= data.size());
        std::string text(data.begin() + cursor, data.begin() + cursor + length);
        cursor += length; return Bytes(text);
    }
};
struct QDataStream {
    Device d;
    Device* device() { return &d; }
    template<class T> QDataStream& operator>>(T& value) {
        assert(d.cursor + sizeof(T) <= d.data.size());
        uint64_t raw = 0;
        for (size_t i = 0; i < sizeof(T); ++i) raw |= uint64_t(d.data[d.cursor++]) << (i * 8);
        value = static_cast<T>(raw); return *this;
    }
};
int propertyReads = 0;
int32_t parseBinaryFBXProperty(QDataStream& in, int& position) {
    quint8 tag; int32_t value;
    in >> tag >> value;
    assert(tag == 'I');
    position += 5; ++propertyReads; return value;
}
''' + parser + r'''
// Build a binary FBX node tree independently of the parser under test.
struct Input {
    std::string name;
    int32_t value;
    std::vector<Input> children;
};
void writeAt(std::vector<uint8_t>& out, size_t offset, uint64_t value, size_t width) {
    for (size_t i = 0; i < width; ++i) out.at(offset + i) = (value >> (i * 8)) & 255;
}
void appendNode(std::vector<uint8_t>& out, const Input& node, bool wide) {
    const size_t width = wide ? 8 : 4, header = 3 * width + 1, start = out.size();
    out.resize(start + header);
    out[start + 3 * width] = node.name.size();
    out.insert(out.end(), node.name.begin(), node.name.end());
    out.push_back('I');
    const auto propertyStart = out.size(); out.resize(propertyStart + 4);
    writeAt(out, propertyStart, node.value, 4);
    for (const auto& child : node.children) appendNode(out, child, wide);
    if (!node.children.empty()) out.resize(out.size() + header, 0); // null sentinel
    writeAt(out, start, out.size(), width);
    writeAt(out, start + width, 1, width);
    writeAt(out, start + 2 * width, 5, width);
}
void expect(const FBXNode& node, const char* name, int value) {
    assert(node.name == name);
    assert(node.properties.size() == 1 && node.properties[0] == value);
}
void test(bool wide, bool enabled, bool sequential = false, bool seekWorks = true) {
    Input curve {"AnimationCurve", 10, {
        {"KeyTime", 11, {}}, {"KeyAttrFlags", 12, {}},
        {"KeyAttrDataFloat", 13, {}}, {"KeyAttrRefCount", 14, {}},
        {"KeyValueFloat", 15, {}}, {"Default", 16, {}},
        {"Nested", 17, {{"KeyTime", 18, {}}}}
    }};
    QDataStream in; in.d.data.resize(27, 0);
    in.d.sequential = sequential; in.d.seekWorks = seekWorks;
    appendNode(in.d.data, {"Objects", 1, {curve,
        {"AnimationCurveNode", 20, {{"KeyTime", 21, {}}}},
        {"KeyAttrFlags", 22, {}}}}, wide);
    const int rootEnd = in.d.data.size();
    appendNode(in.d.data, {"KeyTime", 30, {}}, wide); // next top-level sibling
    const int siblingEnd = in.d.data.size();
    in.d.data.resize(in.d.data.size() + (wide ? 25 : 13), 0);
    int position = 27; propertyReads = 0;
    auto root = parseBinaryFBXNode(in, position, wide, enabled);
    assert(position == rootEnd && in.d.cursor == size_t(rootEnd));
    expect(root, "Objects", 1); assert(root.children.size() == 3);
    const bool skipped = enabled && !sequential && seekWorks;
    const auto& actualCurve = root.children[0];
    expect(actualCurve, "AnimationCurve", 10);
    assert(actualCurve.children.size() == (skipped ? 3 : 7));
    const size_t firstKept = skipped ? 0 : 4;
    if (!skipped) {
        expect(actualCurve.children[0], "KeyTime", 11);
        expect(actualCurve.children[1], "KeyAttrFlags", 12);
        expect(actualCurve.children[2], "KeyAttrDataFloat", 13);
        expect(actualCurve.children[3], "KeyAttrRefCount", 14);
    }
    expect(actualCurve.children[firstKept], "KeyValueFloat", 15);
    expect(actualCurve.children[firstKept + 1], "Default", 16);
    const auto& nested = actualCurve.children[firstKept + 2];
    expect(nested, "Nested", 17); assert(nested.children.size() == 1);
    expect(nested.children[0], "KeyTime", 18); // not a direct curve child
    expect(root.children[1], "AnimationCurveNode", 20);
    assert(root.children[1].children.size() == 1);
    expect(root.children[1].children[0], "KeyTime", 21);
    expect(root.children[2], "KeyAttrFlags", 22);
    auto sibling = parseBinaryFBXNode(in, position, wide, enabled);
    expect(sibling, "KeyTime", 30);
    assert(position == siblingEnd && in.d.cursor == size_t(siblingEnd));
    assert(propertyReads == (skipped ? 10 : 14));
    assert(in.d.successfulSeeks == (skipped ? 4 : 0));
    auto sentinel = parseBinaryFBXNode(in, position, wide, enabled);
    assert(sentinel.name.isNull());
    assert(position == int(in.d.data.size()) && in.d.cursor == in.d.data.size());
}
int main() {
    for (bool wide : {false, true}) {
        test(wide, false);
        test(wide, true);
        test(wide, true, true);
        test(wide, true, false, false);
    }
}
'''
with tempfile.TemporaryDirectory() as tmp:
    cpp = Path(tmp) / 'test.cpp'
    cpp.write_text(fixture)
    exe = Path(tmp) / 'test'
    subprocess.run(['c++', '-std=c++14', '-O2', '-Wall', '-Wextra',
                    str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS: actual recursive node parser, 32/64-bit headers, sibling alignment, '
      'direct-child scope, full mode, sequential/failed-seek fallback')
