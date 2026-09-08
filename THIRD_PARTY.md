# Distribution components

The package contains separately licensed components. Bundling an executable does
not remove its license, and the included license notices must accompany every
redistribution. CrabVault does not include FModel, WinRAR, the RAD Video Tools
encoder, or game files. The official Bink Player is included unmodified for
non-commercial BK2 preview and retains the credit displayed by the utility.

| Component | Purpose | License / official source |
| --- | --- | --- |
| Python | Runs CrabVault inside the package | PSF; https://www.python.org/psf/license/ |
| pywebview | Desktop window and interface bridge | BSD-3-Clause; https://github.com/r0x0r/pywebview |
| pythonnet | WinForms integration | MIT; https://github.com/pythonnet/pythonnet |
| Pillow | Images and thumbnails | HPND; https://github.com/python-pillow/Pillow |
| Three.js | 3D rendering | MIT; license in `frontend/vendor/three/LICENSE.txt` |
| .NET 8 / .NET 10 | Private runtimes for UAssetTool and the 3D extractor | MIT and Microsoft notices; `tools/dotnet8/LICENSE.txt` and `ThirdPartyNotices.txt`; https://github.com/dotnet/runtime |
| CUE4Parse / conversion | Reads Unreal containers and assets | Apache-2.0; bundled `LICENSE` and `NOTICE`; https://github.com/FabianFG/CUE4Parse |
| Oodle Data 2.9.10 | Decompresses game containers; downloaded on demand and not shipped | Proprietary Epic/RAD software; pinned WorkingRobot/OodleUE source and hash; https://github.com/WorkingRobot/OodleUE |
| UAssetToolRivals | Lists assets | GPL-3.0; `tools/uassettool/LICENSE.txt`; https://github.com/XzantGaming/UassetToolRivals |
| 7-Zip 26.02 | Extracts RAR/7z files | LGPL with unRAR restriction; `tools/7zip/License.txt`; https://github.com/ip7z/7zip/tree/26.02 |
| vgmstream r2117 | Wwise audio preview | Licenses in `tools/vgmstream/COPYING`; https://github.com/vgmstream/vgmstream/tree/r2117 |
| HandBrakeCLI 1.11.2 | Converts gallery videos | GPL-2.0 and bundled component licenses; https://github.com/HandBrake/HandBrake/tree/1.11.2 |
| Bink Player 2026.06 | BK2 video preview | Official RAD/Epic utility; free redistribution only for non-commercial use with the RAD credit preserved; https://www.radgametools.com/binkfaq.htm |
| WebView2 Evergreen | Shared browser runtime for the interface | Microsoft terms; bootstrapper and updates supplied by Microsoft; https://developer.microsoft.com/microsoft-edge/webview2/ |
| MarvelRivalsCharacterIDs | Character and skin IDs/names queried at runtime | Attribution: https://github.com/donutman07/MarvelRivalsCharacterIDs; the repository declared no license when reviewed |

## Preparation and security

`dependencies.lock.json` records reviewed official URLs and SHA-256 values.
GitHub package hashes were checked against official release digests. WebView2 is
not bundled: its Evergreen bootstrapper is downloaded from Microsoft over HTTPS,
and its Microsoft Authenticode signature is verified before execution. The .NET
8.0.30 Runtime ZIP was checked against the official SHA-512 published at
https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json
before its SHA-256 was recorded in the lock file.

Distribution dependencies are downloaded only by the preparation script, never
during mod import. The script extracts files without running their installers.
Tool DLLs and executables remain in their own directories.

WebView2 Evergreen is shared with other applications and receives Microsoft
updates. CrabVault checks it before creating the application window. Distribution
requirements are documented at:
https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution

## Limitations that must remain disclosed

- The initial target is Windows 11 x64. WinForms uses the .NET Framework supplied
  with Windows; the modern .NET runtime used by the extractor is bundled.
- Corporate policies may prevent WebView2 installation or updates.
- BK2 preview launches the bundled official Bink Player in its own window and
  preserves the RAD credit. FFmpeg still reports that Bink 2 is not implemented:
  https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/bink.c
- License files do not replace corresponding source when a license requires it.
  Corresponding GPL/LGPL source must accompany the applicable binaries. Rights
  for catalogs, icons, and mappings must be reviewed separately.
- MarvelRivalsCharacterIDs is public but declares no license. Runtime access and
  attribution do not automatically grant redistribution rights.

## Materials accompanying a public release

The technical bundle is not by itself a complete compliance review. Follow the
private source repository's `RELEASE_CHECKLIST.md` for every release.

This command creates a separate archive containing locked corresponding source,
a manifest, and hashes without executing downloaded content:

`python tools/packaging/prepare_corresponding_sources.py --version 0.44.11 --offline`

The archive includes CUE4Parse, UAssetToolRivals, HandBrake 1.11.2, and 7-Zip
26.02, plus the patch and build recipe for the sanitized UAssetTool binary.
Versions and hashes are recorded in `THIRD_PARTY_COMPONENTS.json`.

- Publish the exact UAssetToolRivals GPL-3.0 corresponding source, including its
  pinned commit, patch, recipe, and expected binary hash.
- Publish HandBrakeCLI 1.11.2 corresponding source under GPL-2.0 and the bundled
  library terms.
- Preserve 7-Zip 26.02 attribution/source under LGPL and the unRAR restriction.
- Preserve the CUE4Parse `LICENSE` and `NOTICE` and all required runtime notices.
  `NUGET_DEPENDENCIES.json` is an inventory, not a replacement for license text.
- Keep CrabVault's proprietary terms separate from third-party licenses.

The MIT notices for `Oodle.NET` and `OodleSharp` do not change the terms of the
native Oodle DLL. Version 2.9.10 has a pinned source, commit, SHA-256, and notice.
The DLL is not included in the ZIP. When the user requests 3D setup, CrabVault
downloads it directly from WorkingRobot/OodleUE, validates it, and records the
source. The repository maintainer disclaims ownership and refers users to the
Unreal Engine EULA. See https://www.radgametools.com/oodle.htm and
https://www.unrealengine.com/eula/unreal.
