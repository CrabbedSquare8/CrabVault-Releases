using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;
using CUE4Parse.UE4.Assets.Exports.Material;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse.UE4.Versions;
using CUE4Parse_Conversion.Textures;
using SkiaSharp;

namespace MarvelManager.Native3D;

internal sealed class PreviewTextures(string outputDirectory, ETexturePlatform platform,
    HashSet<string> gpuFormats)
{
    private readonly Dictionary<string, UTexture2D> _textures = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _materials = new(StringComparer.OrdinalIgnoreCase);
    public List<string> Failures { get; } = [];

    public void AddMaterial(UMaterialInterface material)
    {
        if (!_materials.Add(material.GetPathName())) return;
        try
        {
            var parameters = new CMaterialParams2();
            material.GetParams(parameters, EMaterialFormat.AllLayersNoRef);
            var references = new Dictionary<string, string>();
            foreach (var (key, texture) in parameters.Textures)
            {
                references[key] = texture.GetPathName();
                if (texture is UTexture2D texture2D) AddTexture(texture2D);
            }
            var owner = material.Owner!;
            var path = Program.OutputPath(outputDirectory, owner.Provider!.FixPath(owner.Name), ".json");
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, JsonSerializer.Serialize(new {
                Textures = references, Parameters = new { parameters.IsTranslucent }
            }));
        }
        catch (Exception exception) { Failures.Add($"{material.Name}: {exception.Message}"); }
    }

    public void AddTexture(UTexture2D texture, string? packagePath = null)
    {
        if (texture.Owner is null) return;
        var package = texture.Owner.Provider!.FixPath(packagePath ?? texture.Owner.Name);
        var path = Program.OutputPath(outputDirectory, package, ".png");
        _textures.TryAdd(path, texture);
    }

    public object WriteAll()
    {
        var errors = new ConcurrentQueue<string>();
        var clock = Stopwatch.StartNew();
        var reused = 0;
        var written = 0;
        var gpuWritten = 0;
        // Bounded parallelism: a full-resolution 8K map may need hundreds of MB.
        Parallel.ForEach(_textures, new ParallelOptions { MaxDegreeOfParallelism = 2 }, pair =>
        {
            try
            {
                var format = OriginalTextureWriter.FormatName(pair.Value);
                if (platform == ETexturePlatform.DesktopMobile && format is not null && gpuFormats.Contains(format))
                {
                    var originalPath = Path.ChangeExtension(pair.Key, ".mmtx");
                    if (File.Exists(originalPath) && new FileInfo(originalPath).Length > 32)
                    {
                        Interlocked.Increment(ref reused);
                        return;
                    }
                    if (OriginalTextureWriter.Write(pair.Value, format, originalPath))
                    {
                        Interlocked.Increment(ref gpuWritten);
                        Interlocked.Increment(ref written);
                        return;
                    }
                }
                if (File.Exists(pair.Key) && new FileInfo(pair.Key).Length > 32)
                {
                    Interlocked.Increment(ref reused);
                    return;
                }
                var decoded = pair.Value.Decode(platform);
                if (decoded is null) throw new InvalidDataException("A textura não pôde ser decodificada.");
                using var bitmap = decoded.ToSkBitmap();
                using var pixels = bitmap.PeekPixels();
                var temporary = pair.Key + ".tmp";
                Directory.CreateDirectory(Path.GetDirectoryName(pair.Key)!);
                using (var stream = File.Create(temporary))
                {
                    // Lossless, original resolution. Avoid expensive archive-grade
                    // compression for temporary local preview images.
                    if (!pixels.Encode(stream, new SKPngEncoderOptions(SKPngEncoderFilterFlags.Sub, 1)))
                        throw new InvalidDataException("Não foi possível preparar o PNG da textura.");
                }
                File.Move(temporary, pair.Key, true);
                Interlocked.Increment(ref written);
            }
            catch (Exception exception) { errors.Enqueue($"{pair.Value.Name}: {exception.Message}"); }
        });
        Failures.AddRange(errors);
        return new { written, reused, gpu_written = gpuWritten, seconds = clock.Elapsed.TotalSeconds };
    }
}
