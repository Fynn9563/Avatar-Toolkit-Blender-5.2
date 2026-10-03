# Avatar Toolkit
This local compatibility update (0.5.5) targets Blender 5.2.2 LTS.
Install `avatar_toolkit-0.5.5.zip` through **Edit > Preferences > Get Extensions > Install from Disk**.
Restart Blender after replacing an older copy.

Compatibility checks run in Blender 5.2.2 include repeated registration and cleanup,
PMX mesh/armature/material import, VMD bone/IK/camera/light animation, NLA slots,
camera baking, MMD shader conversion, STL import, and FBX/glTF export.
Pose mode and shape-key-to-basis geometry checks also pass. The packaged Windows
LZ4 wheel passes a compression/decompression check inside Blender's Python 3.13.
Bundled LZ4 binaries have been replaced with genuine Python 3.13 wheels from
[PyPI](https://pypi.org/project/lz4/4.4.5/); macOS and Linux binaries were inspected
for matching ABI tags but were not executed on those platforms.
The VMD parser was restored from the GPL-licensed
[MMD Tools project](https://github.com/MMD-Blender/blender_mmd_tools).
PMD, VPD and MMD-format exports remain unsupported by this add-on.
VRM, Source, 3DS and X3D imports require their respective external importers.

To rerun the compatibility checks:
```powershell
& 'E:\SteamLibrary\steamapps\common\Blender\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/blender_compatibility.py
```

We are aware the wiki is down and are working on a new one, please don't report this.

## Avatar Toolkit is in Alpha, There will be issues, please ensure you report them!. If using a Alpha plugin isn't your fancy you can find Cats Blender Plugin [HERE](https://github.com/unofficalcats/Cats-Blender-Plugin-Unofficial-)!
#### Avatar Toolkit is in Alpha and will contain issues, please ensure you report them!

Avatar Toolkit is a modern, Blender addon designed to streamline the process of preparing 3D avatars for virtual platforms including VRChat, ChilloutVR, Resonite, and other similar applications.

# No longer maintained, neoneko has ceased all operations. 

## What is Avatar Toolkit?
Avatar Toolkit simplifies the workflow for avatar creation and optimization by providing an all-in-one solution that:
- Automates complex optimization processes like mesh joining and vertex merging.
- Provides advanced tools for eye tracking setup and viseme configuration.
- Offers specialized armature utilities including bone name conversion for different platforms.
- Includes performance-focused optimization tools so you can optimize your avatar for platforms like VRChat and ChilloutVR.

The addon is built with a focus on user experience, reducing the number of steps needed to prepare avatars while offering powerful customization options for advanced users. Avatar Toolkit aims to be a complete replacement for Cats Blender Plugin and its unofficial variants, with a modern codebase designed specifically for current Blender versions and minimal dependencies on third-party plugins.

Join the Neoneko Discord here: https://discord.neoneko.xyz

Need a more stable toolset while Avatar Toolkit is in Alpha? Then please use Blender 4.x and use our Unofficial Cats Blender Plugin which you can find [here](https://github.com/unofficalcats/Cats-Blender-Plugin-Unofficial-).

### Support us:
If you like what we do and want to help support the development of cats you can do it on our pally.gg [here](https://pally.gg/p/teamneoneko) all money is split automatically between all developers and any support is appreciated.

## Blender version support policies. 

You can find them on the wiki here [HERE](https://avatartoolkit.xyz/legacywiki.html?version=0.2.1#what-is-avatar-toolkits-version-support-policy)

## Features 

See everything Avatar Toolkit has ot offer [here](https://avatartoolkit.xyz/legacywiki.html)

## Requirements

1) Blender Version
- Blender 5.0 or newer is required
- Blender 5.2.2 LTS is the recommended version for this update

2) Python Requirements
- If using a custom Python installation with Blender, ensure NumPy is installed
- Default Blender installation includes all required packages

3) Recommended Setup
- Download Blender directly from https://blender.org
- Use Blender 5.2.2 LTS for the best experience

#### Unfortunately, due to the increased number of people complaining to me (yes, we get DMs about this) that AT or CATS is broken when it's not, we are going to have to be a bit more strict about which Blender releases we will provide support for.

#### We only support the following Blender releases:
- Steam release
- The Blender website releases (there are downloads for Linux, Mac, and Windows)

#### We do not support the following what so ever and we will not give help if your running the following.
- We do not support the Windows Store due to it causing issues, and we also don't support the Snap Store for Linux.
- We do not support package manager releases on Linux. This is because package managers are normally run by the distro, and a lot of the time the distro will build Blender themselves and make their own changes which are not sanctioned by Blender (for example, bundling a newer version of Python which tends to break plugins). If you report a bug from anything apart from the Blender versions we support, you will be told we can't help you from now on.

#### Additional Plugins Requirements.
Currently None.

## Installation
You can find out how to install Avatar Toolkit [here](https://avatartoolkit.xyz/legacywiki.html?version=0.2.0#how-to-install-avatar-toolkit)

## Help

If you need help with Avatar Toolkit you can check the wiki (Coming soon).

## Acknowledgements

Avatar Toolkit is partly based on some code from Cats Blender Plugin and Cats Blender Plugin Unofficial, therefore we want to acknowledge the following people:

### Cats Code contributors:
- absolute quantum
- Hotox
- Shotariya
- Neitri
- Kiraver
- Jordo
- Ruubick
- Mysteryem
- 989onan
- Yusarina

## Feedback

Please open an issue if you need to leave feedback.
