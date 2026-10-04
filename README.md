# Avatar Toolkit for Blender 5.2

A maintained fork of Avatar Toolkit for preparing avatars for VRChat, Resonite, and similar platforms. This fork contains Blender 5.2 compatibility fixes and downloads updates from this repository.

**Current release:** 0.5.7

**Tested runtime:** Blender 5.2.2 LTS on Windows, Python 3.13.13

## Installation

1. Open [Releases](https://github.com/Fynn9563/Avatar-Toolkit-Blender-5.2/releases) and download `avatar_toolkit-0.5.7.zip` from the release assets. Use the extension ZIP rather than GitHub's source-code ZIP.
2. In Blender, open **Edit > Preferences > Get Extensions** and choose **Install from Disk** from the menu.
3. Select the ZIP, enable Avatar Toolkit, and restart Blender if replacing an older installation.
4. Open the **Avatar Toolkit** tab in the 3D Viewport sidebar (`N`).

The package includes LZ4 dependency wheels for Blender's Python 3.13. NumPy is supplied by the tested Blender installation; no separate Python setup is needed for that installation.

The manifest accepts Blender **5.0.0 up to, but excluding, 5.3.0**. Execution testing was performed on **5.2.2 LTS for Windows**. Other Blender versions and macOS/Linux runtimes have not been verified by these tests.

## Updates

Releases are published in [this repository](https://github.com/Fynn9563/Avatar-Toolkit-Blender-5.2/releases). Download the extension ZIP from the release assets and install it through Blender's **Install from Disk** menu. Restart Blender after replacing an older version.

UI version labels read the package manifest. For the current test results and update-path coverage, see [TEST_REPORT.md](TEST_REPORT.md).

## Features

- Mesh joining, separation, attachment, transforms, and shape-key utilities.
- Viseme generation, eye tracking, and blink/lowerlid setup.
- Armature validation, bone cleanup and merging, digitigrade conversion, and pose tools.
- Rigify, VRM, and Resonite bone conversion.
- Material consolidation, texture atlases, UV alignment, and seam tools.
- Offline dictionary translation, with optional external translation services.
- PMX models, VMD animation, STL import, and Blender FBX/glTF export workflows.
- Resonite AnimX animation import, including raw, LZ4, and LZMA encodings.

**Integration limits:** VRM, Source, 3DS, and X3D file imports require their respective external importers. VRM bone conversion is a separate tool included in this fork. DeepL/LibreTranslate services require their own credentials or configured server. PMD/VPD import and MMD-format export remain unsupported.

## Testing

Version 0.5.7 passed **44 automated feature scenarios**, the compatibility suite, and Blender extension build/validation checks. Across the feature and compatibility suites, **61 distinct add-on operators** were executed. All **160 registered operators** passed polling checks across multiple contexts. The release download and isolated update installation checks also passed.

These checks do not establish exhaustive coverage of every function or input. Interactive dialogs, production avatars, real-time viewport behavior, live translation services, third-party importers, and some bundled MMD editing tools still need manual or external integration testing. See [TEST_REPORT.md](TEST_REPORT.md) and the [operator coverage inventory](tests/operator_coverage.json) for details.

Run from the repository root with your Blender executable:

```powershell
$blenderPath = 'E:\SteamLibrary\steamapps\common\Blender\blender.exe'
& $blenderPath --background --factory-startup --python-exit-code 1 --python tests/blender_extended_suite.py
& $blenderPath --background --factory-startup --python-exit-code 1 --python tests/blender_compatibility.py
```

Tests create synthetic scenes and write fixtures/results into `.validation/`. Use `--factory-startup` to isolate them from your saved startup scene. Package checks and build commands are documented in [TEST_REPORT.md](TEST_REPORT.md).

## Issues

Report problems in [this repository's issue tracker](https://github.com/Fynn9563/Avatar-Toolkit-Blender-5.2/issues). Include the add-on version, Blender version, operating system, reproduction steps, and any traceback. Include a small reproduction file when possible.

## License and acknowledgements

Licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE).

This fork builds on [Avatar Toolkit](https://github.com/teamneoneko/Avatar-Toolkit) and code from Cats Blender Plugin and its unofficial variants. The restored VMD parser comes from the GPL-licensed [MMD Tools project](https://github.com/MMD-Blender/blender_mmd_tools). Bundled LZ4 wheels are version 4.4.5.

Acknowledged Cats contributors: absolute quantum, Hotox, Shotariya, Neitri, Kiraver, Jordo, Ruubick, Mysteryem, 989onan, and Yusarina.
