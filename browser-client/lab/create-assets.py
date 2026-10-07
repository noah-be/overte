#!/usr/bin/env python3
"""Generate an original, textured glTF and separate binary PNG fixtures for actual ATP upload."""
import base64
import json
import pathlib
import struct
import zlib

ROOT = pathlib.Path(__file__).resolve().parent

def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))

png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(bytes([0, 255, 80, 20, 20, 200, 255, 0, 20, 200, 255, 255, 80, 20])))
png += chunk(b"IEND", b"")
# Six faces with separate UVs and normals; 24 vertices, 12 triangles.
positions, normals, uvs, indices = [], [], [], []
faces = [((1, 0, 0), [(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)]),
         ((-1,0,0), [(-1,-1,1),(-1,1,1),(-1,1,-1),(-1,-1,-1)]),
         ((0,1,0), [(-1,1,-1),(-1,1,1),(1,1,1),(1,1,-1)]),
         ((0,-1,0), [(-1,-1,1),(-1,-1,-1),(1,-1,-1),(1,-1,1)]),
         ((0,0,1), [(1,-1,1),(1,1,1),(-1,1,1),(-1,-1,1)]),
         ((0,0,-1), [(-1,-1,-1),(-1,1,-1),(1,1,-1),(1,-1,-1)])]
for i, (normal, vertices) in enumerate(faces):
    positions.extend(v / 2 for vertex in vertices for v in vertex)
    normals.extend(list(normal) * 4)
    uvs.extend([0,0,0,1,1,1,1,0])
    indices.extend(i * 4 + j for j in [0,1,2,0,2,3])
data, views = b"", []
for values, fmt, target in [(positions,"f",34962),(normals,"f",34962),(uvs,"f",34962),(indices,"H",34963)]:
    raw = struct.pack("<" + fmt * len(values), *values)
    views.append({"buffer":0,"byteOffset":len(data),"byteLength":len(raw),"target":target})
    data += raw
gltf = {"asset":{"version":"2.0","generator":"Overte browser laboratory original fixture"},
 "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],
 "buffers":[{"uri":"data:application/octet-stream;base64,"+base64.b64encode(data).decode(),"byteLength":len(data)}],
 "bufferViews":views,"accessors":[
 {"bufferView":0,"componentType":5126,"count":24,"type":"VEC3","min":[-.5,-.5,-.5],"max":[.5,.5,.5]},
 {"bufferView":1,"componentType":5126,"count":24,"type":"VEC3"},
 {"bufferView":2,"componentType":5126,"count":24,"type":"VEC2"},
 {"bufferView":3,"componentType":5123,"count":36,"type":"SCALAR"}],
 "meshes":[{"primitives":[{"attributes":{"POSITION":0,"NORMAL":1,"TEXCOORD_0":2},"indices":3,"material":0}]}],
 "images":[{"uri":"checker.png"}],
 "textures":[{"source":0}],"materials":[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0},"metallicFactor":0,"roughnessFactor":.8}}]}
(ROOT / "textured-cube.gltf").write_text(json.dumps(gltf, separators=(",", ":")) + "\n")
(ROOT / "checker.png").write_bytes(png)
print(ROOT / "textured-cube.gltf")
