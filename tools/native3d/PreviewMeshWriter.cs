using System.Numerics;
using System.Text;
using System.Text.Json;
using CUE4Parse.UE4.Assets.Exports.Material;
using CUE4Parse_Conversion.Meshes.PSK;

namespace MarvelManager.Native3D;

/// <summary>
/// Writes the existing indexed LOD, once per vertex, for the static preview.
/// No triangle welding, animation rig rebuild, decimation or texture resizing.
/// Skeletal vertices are already in the reference pose used by the viewer.
/// </summary>
internal static class PreviewMeshWriter
{
    public static string Write(string name, CBaseMeshLod lod, CMeshVertex[] vertices,
        string destination, Action<UMaterialInterface> collectMaterial)
    {
        if (vertices.Length == 0 || lod.SkipLod)
            throw new InvalidDataException("O Mesh não contém geometria renderizável.");

        using var binary = new MemoryStream();
        using var writer = new BinaryWriter(binary, Encoding.UTF8, true);
        var views = new List<object>();
        var accessors = new List<Dictionary<string, object>>();
        var attributes = new Dictionary<string, int>();
        var minimum = new Vector3(float.PositiveInfinity);
        var maximum = new Vector3(float.NegativeInfinity);

        int AddAccessor(long start, int count, string type, int componentType = 5126,
            int target = 34962)
        {
            var view = views.Count;
            views.Add(new { buffer = 0, byteOffset = start,
                byteLength = binary.Position - start, target });
            var index = accessors.Count;
            accessors.Add(new Dictionary<string, object> {
                ["bufferView"] = view, ["componentType"] = componentType,
                ["count"] = count, ["type"] = type
            });
            return index;
        }

        var start = binary.Position;
        foreach (var vertex in vertices)
        {
            var position = new Vector3(vertex.Position.X, vertex.Position.Z, vertex.Position.Y) * 0.01f;
            if (!float.IsFinite(position.X + position.Y + position.Z))
                throw new InvalidDataException("O Mesh contém uma posição inválida.");
            minimum = Vector3.Min(minimum, position);
            maximum = Vector3.Max(maximum, position);
            writer.Write(position.X); writer.Write(position.Y); writer.Write(position.Z);
        }
        attributes["POSITION"] = AddAccessor(start, vertices.Length, "VEC3");
        accessors[^1]["min"] = new[] { minimum.X, minimum.Y, minimum.Z };
        accessors[^1]["max"] = new[] { maximum.X, maximum.Y, maximum.Z };

        start = binary.Position;
        foreach (var vertex in vertices)
        {
            var normal = new Vector3(vertex.Normal.X, vertex.Normal.Z, vertex.Normal.Y);
            normal = normal.LengthSquared() > 1e-12f ? Vector3.Normalize(normal) : Vector3.UnitY;
            writer.Write(normal.X); writer.Write(normal.Y); writer.Write(normal.Z);
        }
        attributes["NORMAL"] = AddAccessor(start, vertices.Length, "VEC3");

        start = binary.Position;
        foreach (var vertex in vertices)
        {
            var tangent = new Vector3(vertex.Tangent.X, vertex.Tangent.Z, vertex.Tangent.Y);
            tangent = tangent.LengthSquared() > 1e-12f ? Vector3.Normalize(tangent) : Vector3.UnitX;
            writer.Write(tangent.X); writer.Write(tangent.Y); writer.Write(tangent.Z);
            writer.Write(vertex.Tangent.W < 0 ? -1f : 1f);
        }
        attributes["TANGENT"] = AddAccessor(start, vertices.Length, "VEC4");

        // Keep every UV channel; custom materials may select UV2/UV3.
        start = binary.Position;
        foreach (var vertex in vertices) { writer.Write(vertex.UV.U); writer.Write(vertex.UV.V); }
        attributes["TEXCOORD_0"] = AddAccessor(start, vertices.Length, "VEC2");
        var extraUv = lod.ExtraUV?.Value ?? [];
        for (var channel = 0; channel < extraUv.Length; channel++)
        {
            if (extraUv[channel].Length != vertices.Length) continue;
            start = binary.Position;
            foreach (var uv in extraUv[channel]) { writer.Write(uv.U); writer.Write(uv.V); }
            attributes[$"TEXCOORD_{channel + 1}"] = AddAccessor(start, vertices.Length, "VEC2");
        }

        var primitives = new List<object>();
        var materials = new List<object>();
        var materialIndices = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var indices = lod.Indices?.Value ?? throw new InvalidDataException("O Mesh não possui índices.");
        foreach (var section in lod.Sections?.Value ?? [])
        {
            if (section.NumFaces <= 0) continue;
            if (section.FirstIndex < 0 || (long)section.FirstIndex + (long)section.NumFaces * 3 > indices.Length)
                throw new InvalidDataException("O Mesh contém uma seção de índices inválida.");
            UMaterialInterface? material = null;
            try { material = section.Material?.Load<UMaterialInterface>(); }
            catch { /* Geometry remains previewable when a game material cannot be resolved. */ }
            var materialName = material?.Name ?? section.MaterialName ?? $"Material_{section.MaterialIndex}";
            if (!materialIndices.TryGetValue(materialName, out var materialIndex))
            {
                materialIndex = materials.Count;
                materialIndices[materialName] = materialIndex;
                materials.Add(new { name = materialName, doubleSided = true,
                    pbrMetallicRoughness = new { baseColorFactor = new[] { 1, 1, 1, 1 },
                        metallicFactor = 0, roughnessFactor = 0.72 } });
                if (material is not null) collectMaterial(material);
            }
            start = binary.Position;
            for (var face = 0; face < section.NumFaces; face++)
            {
                var offset = section.FirstIndex + face * 3;
                // Preserve the Unreal-to-viewer winding used by CUE4Parse.
                for (var corner = 0; corner < 3; corner++)
                {
                    var index = indices[offset + corner];
                    if (index >= vertices.Length) throw new InvalidDataException("Índice fora do Mesh.");
                    writer.Write(index);
                }
            }
            var accessor = AddAccessor(start, section.NumFaces * 3, "SCALAR", 5125, 34963);
            primitives.Add(new { attributes, indices = accessor, material = materialIndex, mode = 4 });
        }
        if (primitives.Count == 0) throw new InvalidDataException("O Mesh não contém triângulos.");

        var document = new { asset = new { version = "2.0", generator = "Marvel Manager indexed preview" },
            scene = 0, scenes = new[] { new { nodes = new[] { 0 } } },
            nodes = new[] { new { name, mesh = 0 } }, meshes = new[] { new { name, primitives } },
            materials, buffers = new[] { new { byteLength = binary.Length } }, bufferViews = views, accessors };
        var json = JsonSerializer.SerializeToUtf8Bytes(document);
        var jsonLength = (json.Length + 3) & ~3;
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        var temporary = destination + ".tmp";
        using (var output = new BinaryWriter(File.Create(temporary)))
        {
            output.Write(0x46546C67u); output.Write(2u);
            output.Write(checked((uint)(28 + jsonLength + binary.Length)));
            output.Write(jsonLength); output.Write(0x4E4F534Au); output.Write(json);
            for (var padding = json.Length; padding < jsonLength; padding++) output.Write((byte)' ');
            output.Write(checked((uint)binary.Length)); output.Write(0x004E4942u);
            binary.Position = 0;
            binary.CopyTo(output.BaseStream);
        }
        File.Move(temporary, destination, true);
        return destination;
    }
}
