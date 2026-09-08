using System.Diagnostics;
using System.Text.Json;
using CUE4Parse.Compression;
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Exports.SkeletalMesh;
using CUE4Parse.UE4.Assets.Exports.StaticMesh;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse.UE4.Versions;
using CUE4Parse_Conversion.Meshes;
using CUE4Parse_Conversion.Meshes.PSK;

namespace MarvelManager.Native3D;

internal static class Program
{
    private sealed record Model(string Key, string Name, string Package, UObject Asset);

    private static int Main(string[] args)
    {
        var clock = Stopwatch.StartNew();
        var timings = new Dictionary<string, double>();
        try
        {
            var options = ParseArguments(args);
            var archiveDirectory = Required(options, "archives");
            var outputDirectory = Required(options, "output");
            var componentPaths = File.ReadLines(Required(options, "component-containers"))
                .Where(path => !string.IsNullOrWhiteSpace(path)).ToArray();
            var containerNames = componentPaths
                .Select(path => Path.GetFileName(path.Trim()))
                .Where(name => !string.IsNullOrWhiteSpace(name))
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            if (containerNames.Count == 0)
                throw new InvalidDataException("Nenhum pacote do componente foi indicado.");

            ZlibHelper.Initialize(Required(options, "zlib"));
            OodleHelper.Initialize(Required(options, "oodle"));
            // The managed decoder ships with the extractor. On Windows, the
            // default BC7/ETC fallback otherwise requires a separate Detex DLL.
            CUE4Parse_Conversion.Textures.TextureDecoder.UseAssetRipperTextureDecoder = true;
            var version = new VersionContainer(EGame.GAME_MarvelRivals);
            using var provider = new DefaultFileProvider(archiveDirectory, SearchOption.TopDirectoryOnly,
                version, StringComparer.OrdinalIgnoreCase)
            {
                MappingsContainer = new FileUsmapTypeMappingsProvider(Required(options, "mappings"))
            };
            provider.Initialize();
            // Open only the explicitly selected containers, directly from their
            // original disks. No installation, copying or hardlinks in the game.
            var directPaths = componentPaths.Where(Path.IsPathFullyQualified);
            if (options.TryGetValue("global-containers", out var globalList))
                directPaths = directPaths.Concat(File.ReadLines(globalList));
            foreach (var path in directPaths.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                var extension = Path.GetExtension(path);
                if (!extension.Equals(".pak", StringComparison.OrdinalIgnoreCase)
                    && !extension.Equals(".utoc", StringComparison.OrdinalIgnoreCase)) continue;
                if (!File.Exists(path)) throw new FileNotFoundException("Pacote não encontrado.", path);
                provider.RegisterVfs(path);
            }
            provider.Mount();
            provider.PostMount();
            timings["mount"] = clock.Elapsed.TotalSeconds;

            // Discover packages from the selected containers, not the global game
            // index. An empty external asset cache must never scan the game.
            var files = provider.MountedVfs
                .Where(reader => containerNames.Contains(Path.GetFileName(reader.Name)))
                .SelectMany(reader => reader.Files.Values)
                .Where(file => file.Path.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase))
                .DistinctBy(file => file.Path, StringComparer.OrdinalIgnoreCase)
                .OrderBy(file => file.Path, StringComparer.OrdinalIgnoreCase).ToArray();
            if (files.Length == 0)
                throw new InvalidDataException("Não encontrei assets legíveis nos pacotes deste componente.");

            var models = new List<Model>();
            var failures = new List<string>();
            var gpuFormats = (options.GetValueOrDefault("gpu-textures") ?? "").Split(',')
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            var textures = new PreviewTextures(outputDirectory, version.Platform, gpuFormats);
            var phase = Stopwatch.StartNew();
            var inspected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            void InspectMeshes(IEnumerable<CUE4Parse.FileProvider.Objects.GameFile> packages)
            {
                foreach (var file in packages)
                {
                    if (!inspected.Add(file.Path)) continue;
                    try
                    {
                        foreach (var asset in provider.LoadPackage(file).GetExports())
                        {
                            if (asset is USkeletalMesh or UStaticMesh)
                                models.Add(new Model(NormalizePackagePath(file.Path) + "." + asset.Name,
                                    asset.Name, file.Path, asset));
                        }
                    }
                    catch (Exception exception) { failures.Add($"{file.Path}: {exception.Message}"); }
                }
            }
            InspectMeshes(files.Where(file => IsLikelyMeshPackage(file.Path)));
            // Arbitrary mod names are supported; fallback is bounded to this component.
            if (models.Count == 0)
                InspectMeshes(files.Where(file => !IsTexturePackage(file.Path) && !IsSupportPackage(file.Path)));
            models = models.OrderBy(model => model.Name.Contains("Lobby", StringComparison.OrdinalIgnoreCase))
                .ThenBy(model => model.Name, StringComparer.OrdinalIgnoreCase).ToList();
            timings["load_packages"] = phase.Elapsed.TotalSeconds;
            if (models.Count == 0)
                return WriteResult(false, new { error = "Nenhum SkeletalMesh ou StaticMesh legível foi encontrado neste componente.", failures });

            var requested = options.GetValueOrDefault("model");
            var selected = string.IsNullOrWhiteSpace(requested) ? models[0]
                : models.FirstOrDefault(model => model.Key.Equals(requested, StringComparison.OrdinalIgnoreCase));
            if (selected is null)
                throw new InvalidDataException("A variante solicitada não pertence a este componente.");

            phase.Restart();
            CBaseMeshLod? lod = null;
            CMeshVertex[]? vertices = null;
            if (selected.Asset is USkeletalMesh skeletal && skeletal.TryConvert(out var skeletalMesh))
            {
                var first = skeletalMesh.LODs.FirstOrDefault(item => !item.SkipLod);
                lod = first; vertices = first?.Verts;
            }
            else if (selected.Asset is UStaticMesh rigid && rigid.TryConvert(out var staticMesh))
            {
                var first = staticMesh.LODs.FirstOrDefault(item => !item.SkipLod);
                lod = first; vertices = first?.Verts;
            }
            if (lod is null || vertices is null)
                throw new InvalidDataException("O Mesh não contém um LOD renderizável.");
            var destination = OutputPath(outputDirectory, NormalizePackagePath(selected.Package) + "/" + selected.Name, ".glb");
            var saved = PreviewMeshWriter.Write(selected.Name, lod, vertices, destination, textures.AddMaterial);
            timings["mesh_conversion"] = phase.Elapsed.TotalSeconds;

            phase.Restart();
            // Preserve custom material overrides that lack standard UE parameter names.
            foreach (var file in files.Where(file => IsTexturePackage(file.Path)))
            {
                try
                {
                    foreach (var asset in provider.LoadPackage(file).GetExports())
                        if (asset is UTexture2D texture) textures.AddTexture(texture, file.Path);
                }
                catch (Exception exception) { failures.Add($"{file.Path}: {exception.Message}"); }
            }
            timings["load_textures"] = phase.Elapsed.TotalSeconds;
            phase.Restart();
            var textureStatistics = textures.WriteAll();
            timings["textures"] = phase.Elapsed.TotalSeconds;
            failures.AddRange(textures.Failures);
            return WriteResult(true, new {
                selected = selected.Key, meshes = new[] { saved },
                models = models.Select(model => new { key = model.Key, name = model.Name }),
                timings, textures = textureStatistics, total_seconds = clock.Elapsed.TotalSeconds,
                selected_packages = files.Length, failures = failures.Take(8).ToArray()
            });
        }
        catch (Exception exception)
        {
            return WriteResult(false, new { error = exception.Message, detail = exception.ToString(), timings });
        }
    }

    private static bool IsSupportPackage(string path)
    {
        var name = Path.GetFileNameWithoutExtension(path);
        return name.Contains("AnimBlueprint", StringComparison.OrdinalIgnoreCase)
            || name.Contains("Skeleton", StringComparison.OrdinalIgnoreCase)
            || name.Contains("Physics", StringComparison.OrdinalIgnoreCase)
            || name.StartsWith("MI_", StringComparison.OrdinalIgnoreCase)
            || name.StartsWith("M_", StringComparison.OrdinalIgnoreCase)
            || name.EndsWith("AnimBp", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsTexturePackage(string path) =>
        Path.GetFileName(path).StartsWith("T_", StringComparison.OrdinalIgnoreCase)
        || path.Contains("/Textures/", StringComparison.OrdinalIgnoreCase)
        || path.Contains("/Texture/", StringComparison.OrdinalIgnoreCase);

    private static bool IsLikelyMeshPackage(string path)
    {
        if (IsSupportPackage(path) || IsTexturePackage(path)) return false;
        var name = Path.GetFileName(path);
        return path.Contains("/Meshes/", StringComparison.OrdinalIgnoreCase)
            || path.Contains("/Mesh/", StringComparison.OrdinalIgnoreCase)
            || name.StartsWith("SK_", StringComparison.OrdinalIgnoreCase)
            || name.StartsWith("SM_", StringComparison.OrdinalIgnoreCase)
            || name.Contains("Mesh", StringComparison.OrdinalIgnoreCase);
    }

    private static string NormalizePackagePath(string value)
    {
        var path = value.Replace('\\', '/').TrimStart('/');
        if (path.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)) path = path[..^7];
        return path;
    }

    internal static string OutputPath(string outputDirectory, string package, string extension)
    {
        var root = Path.GetFullPath(outputDirectory) + Path.DirectorySeparatorChar;
        var relative = NormalizePackagePath(package).Replace('/', Path.DirectorySeparatorChar);
        var path = Path.GetFullPath(Path.Combine(root, relative + extension));
        if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("O caminho exportado pelo pacote é inválido.");
        return path;
    }

    private static Dictionary<string, string> ParseArguments(string[] args)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var index = 0; index + 1 < args.Length; index += 2)
            if (args[index].StartsWith("--", StringComparison.Ordinal)) result[args[index][2..]] = args[index + 1];
        return result;
    }

    private static string Required(IReadOnlyDictionary<string, string> options, string name)
    {
        if (options.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value)) return value;
        throw new ArgumentException($"Parâmetro obrigatório ausente: --{name}");
    }

    private static int WriteResult(bool ok, object value)
    {
        var payload = new Dictionary<string, object?> { ["ok"] = ok };
        foreach (var property in value.GetType().GetProperties()) payload[property.Name] = property.GetValue(value);
        Console.WriteLine(JsonSerializer.Serialize(payload));
        return ok ? 0 : 1;
    }
}
