# CrabVault Releases

Official distribution channel for CrabVault on Windows 11 x64.

CrabVault is a free, non-commercial, unofficial mod manager for Marvel Rivals. This repository contains release installers, optional SHA-256 integrity files, release notes, and the notices and corresponding source required for distributed third-party components. The proprietary CrabVault source code is not published here.

## Download and installation

Open the [Releases](https://github.com/CrabbedSquare8/CrabVault-Releases/releases) page and download `CrabVault-vX.Y.Z-windows-x64-setup.exe` from the latest release.

The Windows SmartScreen warning may appear because the installer is not currently digitally signed. Only download CrabVault from this repository.

CrabVault uses the shared Microsoft WebView2 Evergreen Runtime. If it is missing or too old, CrabVault explains why it is needed and asks for permission before downloading and installing the official Microsoft runtime.

## Optional SHA-256 verification

Manual SHA-256 verification is optional. It confirms that your downloaded installer matches the file published here, but it does not replace a digital signature or any software license.

To verify a download in PowerShell:

```powershell
Get-FileHash .\CrabVault-vX.Y.Z-windows-x64-setup.exe -Algorithm SHA256
```

Compare the result with the matching `.sha256` file. Do not run the installer if the values differ. CrabVault's built-in updater performs this verification automatically.

## Privacy

CrabVault has no account system, advertising, telemetry, or analytics. Catalogs, settings, mods, media, and backups remain on the user's computer. Some optional features contact GitHub, Rivalskins, Microsoft, or pinned third-party download sources; the application does not upload the user's mod library or game files.

## License and third-party components

CrabVault is free to use for non-commercial purposes but is not open-source software. The application terms and privacy notice are included with the installer. Third-party components remain under their own licenses, and the required notices and corresponding GPL/LGPL source archives accompany applicable releases.

The bundled Bink Player is the official, unmodified RAD/Epic utility and retains its visible credit as required for free non-commercial redistribution.

## Unofficial project notice

CrabVault is an independent, unofficial, fan-made project. It is not affiliated with, sponsored by, endorsed by, or connected to Marvel, NetEase Games, Epic Games, RAD Game Tools, Rivalskinsk, Nexus Mods, or third-party mod authors.

Marvel Rivals and all related names, characters, trademarks, and materials are the property of their respective owners. Rights holders may submit attribution or removal requests through this repository.