# Avatar Toolkit for Blender 5.2

A maintained fork of Avatar Toolkit for preparing avatars for VRChat, Resonite, and similar platforms. This fork contains Blender 5.2 compatibility fixes and downloads updates from this repository.

**Current release:** 0.6.0

**Target Blender version:** 5.2.2 LTS

## Installation

1. Open [Releases](https://github.com/Fynn9563/Avatar-Toolkit-Blender-5.2/releases) and download `avatar_toolkit-0.6.0.zip` from the release assets. Use the extension ZIP rather than GitHub's source-code ZIP.
2. In Blender, open **Edit > Preferences > Get Extensions** and choose **Install from Disk** from the menu.
3. Select the ZIP, enable Avatar Toolkit, and restart Blender if replacing an older installation.
4. Open the **Avatar Toolkit** tab in the 3D Viewport sidebar (`N`).

The package includes LZ4 dependency wheels for Blender's Python 3.13. Use Blender's bundled Python and NumPy; no separate Python setup is required.

The extension manifest accepts Blender **5.0.0 up to, but excluding, 5.3.0**.

## Updates

The built-in updater checks [this repository's public releases](https://github.com/Fynn9563/Avatar-Toolkit-Blender-5.2/releases) without a GitHub login. You can also download the extension ZIP from the release assets and install it through Blender's **Install from Disk** menu. Restart Blender after replacing an older version.

## Features

- Mesh joining, separation, attachment, transforms, and shape-key utilities.
- Viseme generation, eye tracking, and blink/lowerlid setup.
- Armature validation, bone cleanup and merging, digitigrade conversion, and pose tools.
- Armature merge preview with explicit source and destination selection, compatible bone matching, conflict renaming, and accessory root attachment to Hips or another chosen bone.
- Humanoid bone assignment editor with body, head, and hand sections; optional reparenting and bone-length normalization.
- Rigify, VRM, and Resonite bone conversion.
- Material consolidation, texture atlases, UV alignment, and seam tools.
- Offline dictionary translation, with optional external translation services.
- PMX models, VMD animation, STL import, and Blender FBX/glTF export workflows.
- Resonite AnimX animation import, including raw, LZ4, and LZMA encodings.

**Integration limits:** VRM, Source, 3DS, and X3D file imports require their respective external importers. VRM bone conversion is a separate tool included in this fork. DeepL/LibreTranslate services require their own credentials or configured server. PMD/VPD import and MMD-format export remain unsupported.

## Issues

Report problems in [this repository's issue tracker](https://github.com/Fynn9563/Avatar-Toolkit-Blender-5.2/issues). Include the add-on version, Blender version, operating system, reproduction steps, and any traceback. Include a small reproduction file when possible.

## License and acknowledgements

Licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE).

This fork builds on [Avatar Toolkit](https://github.com/teamneoneko/Avatar-Toolkit) and code from Cats Blender Plugin and its unofficial variants. The restored VMD parser comes from the GPL-licensed [MMD Tools project](https://github.com/MMD-Blender/blender_mmd_tools). Bundled LZ4 wheels are version 4.4.5.

Acknowledged Cats contributors: absolute quantum, Hotox, Shotariya, Neitri, Kiraver, Jordo, Ruubick, Mysteryem, 989onan, and Yusarina.
