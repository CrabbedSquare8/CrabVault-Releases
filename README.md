<div align="center">
  <img src="frontend/assets/crabvault.ico" alt="CrabVault logo" width="112">

  <h1>CrabVault</h1>
  <p><strong>A focused Marvel Rivals mod manager for Windows</strong></p>
  <p>Organize, inspect, activate, and protect your local mod library from one place.</p>
  <p>
    <a href="https://github.com/CrabbedSquare8/CrabVault-Releases/releases/latest"><img src="https://img.shields.io/github/v/release/CrabbedSquare8/CrabVault-Releases?display_name=tag&amp;style=for-the-badge&amp;color=ef3340&amp;label=release" alt="Latest release"></a>
    <a href="https://github.com/CrabbedSquare8/CrabVault-Releases/releases/latest"><img src="https://img.shields.io/github/downloads/CrabbedSquare8/CrabVault-Releases/latest/CrabVault-v0.44.11-windows-x64-setup.exe?displayAssetName=false&amp;style=for-the-badge&amp;color=bd1531&amp;label=installer%20downloads" alt="Installer downloads"></a>
    <img src="https://img.shields.io/badge/platform-Windows_11_x64-1674b8?style=for-the-badge" alt="Windows 11 x64">
    <img src="https://img.shields.io/badge/license-source--available-6f42c1?style=for-the-badge" alt="Source-available license">
  </p>
  <p>
    <a href="https://github.com/CrabbedSquare8/CrabVault-Releases/releases/latest">Download</a> ·
    <a href="#features">Features</a> ·
    <a href="#run-from-source">Run from source</a> ·
    <a href="#privacy">Privacy</a> ·
    <a href="#license-and-notices">License</a>
  </p>
</div>

---

## Features

- Manage local PAK, UCAS, and UTOC mod libraries.
- Enable, disable, organize, and inspect installed mods.
- Detect components, character skins, and potential conflicts.
- Create profiles, backups, and recoverable operation history.
- Manage ReShade packages, cinematics, media, and backgrounds.
- Preview supported assets with the optional built-in 3D viewer.
- Keep user data local, without accounts, advertising, or telemetry.

## Download

The recommended way to use CrabVault is through the official installer on the
[Releases page](https://github.com/CrabbedSquare8/CrabVault-Releases/releases).
Release notes and integrity checksums are published alongside each version.

> [!NOTE]
> Windows SmartScreen may show a warning because current releases are not
> digitally signed.

## Run from source

CrabVault currently targets **Windows 11 x64** and **64-bit Python**.

```powershell
python -m pip install -r requirements.txt
python main.py
```

Optional compatibility tools used by some features retain their own licenses
and notices.

## Privacy

CrabVault has no accounts, advertising, telemetry, or analytics. Settings,
mods, media, and backups remain on the user's computer. Optional features may
contact GitHub, Rivalskins, Microsoft, and pinned third-party sources as
described in the [Privacy Policy](PRIVACY.md).

## Credits

CrabVault was inspired in part by **Repak X** and its focused, user-friendly
approach to mod management. CrabVault is an independent project and is not
affiliated with or endorsed by the Repak X developers.

## License and notices

CrabVault is free and non-commercial. Its original source is publicly readable
under the [CrabVault Source-Available Non-Commercial License](LICENSE.md). This
is a source-available license, not an OSI-approved open-source license.

Third-party components retain their own licenses. See
[`THIRD_PARTY.md`](THIRD_PARTY.md) and the included component
notices for details.

CrabVault is an unofficial fan-made project. It is not affiliated with,
sponsored by, or endorsed by Marvel or NetEase Games. All related trademarks
and materials belong to their respective owners.
