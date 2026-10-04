# Changelog

Changes included in version 0.6.0 of this maintained fork.

## 0.6.0 - 2026-10-04

### Blender compatibility and extension registration

- Target Blender 5.2.2 LTS and declare support for Blender 5.0.0 up to, but excluding, 5.3.0.
- Read both Blender version limits from the extension manifest when enabling the add-on, and show the required range if the running version is incompatible.
- Add shared animation helpers that create or reuse the correct action slot and channel bag for each target, including actions shared by several objects.
- Update VMD, MMD camera baking, AnimX import, and pose flipping to use Blender 5 action slots instead of removed or incompatible animation APIs.
- Track successfully registered classes and modules, unregister them in reverse order, and clean up partial registration after an error.
- Report module import failures and cyclic registration dependencies instead of silently skipping broken features or hanging during registration.
- Avoid registering imported classes or classes Blender has already registered.
- Register atlas material properties during add-on registration and remove them during unregister.
- Avoid duplicate scene handlers and merge-selection timers, and remove the timer when the add-on is disabled.
- Remove the shape-key context-menu entry when the add-on is disabled.

### Model and MMD animation import

- Restore the bundled VMD binary parser from MMD Tools, replacing the incomplete parser in the 0.5.4 package.
- Restore parsing and writing of VMD bone, morph, camera, light, shadow, and property/IK animation data.
- Route VMD imports through the bundled MMD importer instead of an unavailable Tuxedo operator.
- Fix VMD import logging, single-file selection, NLA option forwarding, action-slot assignment for NLA strips, and cancellation/error reporting.
- Use the armature object as the bone-animation target and update IK animation paths for Blender 5.
- Add MMD camera field-of-view and perspective properties, fix the perspective property name, and assign camera animation to the correct objects.
- Fix VMD light animation lookup and target light color and position curves to the correct data blocks.
- Update PMX and rigid-body materials to Blender 5 transparency settings, including transparency overlap handling.
- Update MMD shader conversion to use the Principled BSDF `Transmission Weight` input.
- Use Blender's current STL import operator.
- Fix Source-format import dispatch to call the installed Source importer directly rather than constructing an invalid expression.
- Normalize file extensions to lowercase and handle single-file paths consistently.
- Propagate importer cancellations and report unsupported or failed imports through the existing importer UI.

### Resonite animation and export

- Remove an obsolete glTF export argument that prevented Resonite export with the current Blender exporter.
- Fix AnimX import when the file is selected through `filepath` rather than the multi-file list.
- Create animation curves in the selected target's action slot and report missing target bones clearly.
- Correct scalar track dispatch, vector component mapping, quaternion component order, and quaternion signs during coordinate conversion.
- Convert animation times from seconds to scene frames using the effective scene frame rate.
- Preserve constant interpolation for discrete tracks and hold keys, linear interpolation for linear keys, and Bezier handles for tangent curves.
- Convert tangent values into two-dimensional Blender keyframe handles with the correct timing and coordinate signs.
- Correct AnimX interpolation identifiers, tangent detection, shared interpolation values, and tangent serialization order.
- Reset track/keyframe collections when reading, fix raw-track timing, and replace existing keyframes by their actual time.
- Correct discrete-track serialization and the one-byte AnimX file-version field.
- Fix UTF-8 string byte lengths, unsigned 7-bit integer encoding, nullable-value flags, color decoding, Boolean vector flags, matrix fields, and matrix read methods.
- Replace expression evaluation with explicit type/component lookup in the repaired AnimX paths.
- Repair binary AnimX writing and report invalid track or element types more clearly. Import regression coverage includes raw, LZ4, and LZMA encodings.

### Visemes and eye tracking

- Generate visemes independently for each avatar instead of letting cached shapes from another mesh skip shape-key creation.
- Fix SDK2 blink and lower-lid shape copying to use the selected source shapes and validate missing shape keys.
- Update eye testing, pose clearing, and pose selection to Blender 5 pose-bone APIs.
- Update pose-frame flipping to use the correct action slot, preserve bone selection, and require an active action.

### Materials and texture atlases

- Compare material render settings, node types, input values, images, node groups, texture settings, and links before consolidating materials.
- Preserve materials with different shader graphs instead of modifying textures while checking whether materials match.
- Replace removed texture-node properties with current interpolation and projection properties.
- Remove unused and duplicate material slots while preserving polygon material assignments.
- Process shared materials once during atlas generation.
- Pack larger images first and calculate atlas dimensions from packed image positions, fixing atlases with different image sizes.
- Remap shared mesh data once and restrict atlas mesh processing to the current scene.

### Armature merging

- Add explicit source and destination armature selectors and choose defaults automatically only when exactly two scene rigs make the choice unambiguous.
- Add a merge preview with editable bone mappings and validation before applying the merge.
- Match compatible bones to destination bones while retaining incompatible bones under unique names.
- Allow accessory root bones to attach to a selected destination bone, suggest Hips when unambiguous, or remain unparented.
- Stage merges on copies and verify mesh deformation before replacing the original rigs; cancel and preserve the originals if the combination changes deformation or fails.
- Preserve mesh bindings, vertex weights, shape keys, parenting, supported pose properties, constraints, custom properties, and driver references during merging.
- Retarget supported references and remap vertex groups when source bones are renamed or mapped to destination bones.
- Reject unsafe combinations, including unsupported source animation/drivers, source object constraints, conflicting custom properties, ambiguous mappings, linked data, and incompatible mesh bindings.
- Detect changes to the selected rigs or source bones after preview and require a fresh preview before applying.
- Disable optional mesh joining and cleanup by default. Empty vertex-group cleanup preserves bones.

### Humanoid bone assignments and standardization

- Add an editable humanoid bone assignment editor with body, head, and hand sections, searchable bone slots, Auto Map, and assignment from selected bones.
- Add bone selection from assigned roles, Clear, Revert, required-role counts, hierarchy warnings, and missing/duplicate assignment feedback.
- Store assignments on the armature data and track assigned bone identities so mappings survive renaming and saved Blender files.
- Leave ambiguous automatic matches unassigned for manual review.
- Replace immediate automatic standardization with a review-and-apply workflow that renames explicitly assigned bones.
- Preserve vertex groups, shape-key masks, supported constraints/drivers, and animation references when renaming assigned bones; copy affected actions before changing their paths.
- Make mapped-bone reparenting and bone-length normalization optional and disabled by default, preserving the existing rest pose during ordinary renaming.
- Validate name/group conflicts, invalid data, multiple-rig mesh bindings, and parenting cycles before applying changes, and restore affected state if application fails.

### Updates and version display

- Switch update checks and downloads to this fork's GitHub releases and support public updates without a GitHub login.
- Accept numeric version tags with an optional `v` prefix, compare versions numerically, and restrict automatic updates to the 0.6 release series.
- Ignore drafts, prereleases, incompatible versions, and releases without a correctly named installable extension ZIP.
- Honor Blender Online Access, use normal HTTPS certificate validation, and strip authorization headers when redirecting away from the GitHub API.
- Keep background update checks separate from Blender UI work, completing UI changes through a main-thread timer.
- Validate update archive paths, symbolic links, extension identity, selected version, Blender compatibility, and required dependency wheels before installing.
- Stage update files, back up replaced content, roll back failed installations, and preserve user files outside the managed add-on paths.
- Remove the obsolete private repository notice from the updater UI.
- Read the displayed add-on version from the manifest in English, Japanese, and Korean UI titles instead of hardcoding 0.5.4.
- Show the running Blender version in the main panel and updater.

### Packaging, documentation, and release automation

- Update the manifest maintainer to Fynn9563 and shorten the extension tagline.
- Replace bundled LZ4 binaries with Python 3.13 wheels for Windows, Linux, and macOS; retain LZ4 4.4.5 and use the macOS 10.13 Intel wheel instead of the previous 10.9 filename.
- Exclude nested ZIPs, validation output, tests, Python caches, Git metadata, and workflow files from extension builds. The original ZIP contained another ZIP.
- Rewrite installation, update, feature, issue-reporting, and dependency documentation for the maintained Blender 5.2 fork, and document external importer requirements and unsupported MMD operations.
- Add a changelog for the maintained fork.
- Build an installable extension ZIP automatically when a matching version tag is pushed; reject tag/manifest version mismatches.
- Require package, compatibility, full feature and extended/UI, armature merging, humanoid mapping, and updater tests to pass before publishing the ZIP to a GitHub release.
- Download Blender 5.2.2 LTS for CI and verify its archive checksum before running tests.
- Select the bundled dependency wheel for the test platform and test updater installation using the candidate release ZIP before publication.
- Attach the tested ZIP to the tagged GitHub release, generate notes for a new release, and replace the ZIP asset when rerunning against an existing release.

