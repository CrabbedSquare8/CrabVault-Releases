"""Compare indexed LODs before/after a preview change. Read-only, no exports."""
import argparse
import collections
import json
import pathlib
import struct


def read_glb(path):
    data = pathlib.Path(path).read_bytes()
    assert data[:4] == b"glTF"
    assert len(data) == struct.unpack_from("<I", data, 8)[0]
    offset = 12
    doc, binary = None, None
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        offset += length + 8
    assert doc is not None and binary is not None
    return doc, binary


def accessor(doc, binary, index):
    entry = doc["accessors"][index]
    view = doc["bufferViews"][entry["bufferView"]]
    width = {"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4}[entry["type"]]
    code = {5126:"f",5125:"I",5123:"H",5121:"B"}[entry["componentType"]]
    unpack = struct.Struct("<" + code * width)
    offset = view.get("byteOffset", 0) + entry.get("byteOffset", 0)
    stride = view.get("byteStride", unpack.size)
    return [unpack.unpack_from(binary, offset + n * stride) for n in range(entry["count"])]


def geometry(path):
    doc, binary = read_glb(path)
    triangles = collections.Counter()
    points_uv = set()
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            attrs = primitive["attributes"]
            positions = accessor(doc, binary, attrs["POSITION"])
            uv_names = sorted(name for name in attrs if name.startswith("TEXCOORD_"))
            uvs = {int(name.split('_')[-1]):accessor(doc,binary,attrs[name]) for name in uv_names}
            material = doc["materials"][primitive["material"]]["name"]
            indices = [value[0] for value in accessor(doc,binary,primitive["indices"])]
            for index in indices:
                points_uv.add((material, tuple(round(x,4) for x in positions[index]),
                               tuple(tuple(round(x,4) for x in uvs[channel][index]) if channel in uvs else (0.,0.)
                                     for channel in range(8))))
            for start in range(0,len(indices),3):
                vertices = tuple(sorted(tuple(round(x,4) for x in positions[i]) for i in indices[start:start+3]))
                if len(set(vertices)) == 3:
                    triangles[(material,vertices)] += 1
    return triangles, points_uv


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()
    before, old_uvs = geometry(args.before)
    after, new_uvs = geometry(args.after)
    print(json.dumps({"triangles_before":sum(before.values()),"triangles_after":sum(after.values()),
                      "missing_triangles":sum((before-after).values()),
                      "extra_triangles":sum((after-before).values()),
                      "missing_position_uv_pairs":len(old_uvs-new_uvs),
                      "extra_position_uv_pairs":len(new_uvs-old_uvs)}, indent=2))
    assert not before-after, "Triangles were removed or changed"
    assert not old_uvs-new_uvs, "Positions or UVs were changed"
