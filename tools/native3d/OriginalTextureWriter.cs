using CUE4Parse.UE4.Assets.Exports.Texture;

namespace MarvelManager.Native3D;

/// <summary>Original GPU blocks, not another texture recompression.</summary>
internal static class OriginalTextureWriter
{
    public static string? FormatName(UTexture2D texture)
    {
        // Normal-map reconstruction remains with CUE4Parse's decoder.
        if (texture.IsNormalMap) return null;
        return texture.Format.ToString() switch {
            "PF_DXT1" => "dxt1", "PF_DXT3" => "dxt3",
            "PF_DXT5" => "dxt5", "PF_BC7" => "bc7", _ => null
        };
    }

    public static bool Write(UTexture2D texture, string format, string destination)
    {
        var formatId = format switch { "dxt1" => 1, "dxt3" => 2, "dxt5" => 3, "bc7" => 4, _ => 0 };
        if (formatId == 0) return false;
        var blockBytes = format == "dxt1" ? 8 : 16;
        var mips = new List<(int Width, int Height, byte[] Data)>();
        foreach (var mip in texture.PlatformData.Mips ?? [])
        {
            if (mip.BulkData?.Data is not { Length: > 0 } data) continue;
            if (mip.SizeX <= 0 || mip.SizeY <= 0 || mip.SizeZ > 1) return false;
            var expected = checked(((mip.SizeX + 3) / 4) * ((mip.SizeY + 3) / 4) * blockBytes);
            // Swizzled/virtual/array textures take the compatible PNG path.
            if (data.Length != expected) return false;
            if (mips.Count > 0 && (mip.SizeX != Math.Max(1, mips[^1].Width / 2)
                                || mip.SizeY != Math.Max(1, mips[^1].Height / 2))) break;
            mips.Add((mip.SizeX, mip.SizeY, data));
        }
        if (mips.Count == 0) return false;
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        using (var writer = new BinaryWriter(File.Create(destination + ".tmp")))
        {
            writer.Write(0x58544D4Du); // MMTX
            writer.Write(1); writer.Write(formatId); writer.Write(mips.Count);
            foreach (var mip in mips)
            {
                writer.Write(mip.Width); writer.Write(mip.Height); writer.Write(mip.Data.Length);
                writer.Write(mip.Data);
            }
        }
        File.Move(destination + ".tmp", destination, true);
        return true;
    }
}
