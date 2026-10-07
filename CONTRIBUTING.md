# Contributing

Thanks for helping. Below is everything you need to work on the add-on.

## Project layout

```
open_sky/                  the add-on (this folder is what gets zipped)
  __init__.py              registration, upgrade-on-load handler
  blender_manifest.toml    extension manifest (id, version, license)
  nodekit.py               small DSL for building node trees in Python
  sky.py                   the world shader: atmosphere, moon, stars,
                           Milky Way and aurora node groups
  clouds.py                cloud deck, cirrus, rainbow, halo and lightning
  weather.py               Geometry Nodes rain and snow around the camera
  rig.py                   world, sun/moon lamps and the drivers between them
  presets.py               built-in looks
  props.py / ops.py / ui.py   settings, operators, panels
tools/render_previews.py   renders the preset gallery in docs/images
tests/run_tests.py         headless test suite
```

## Running from source

Point Blender at the repo instead of installing the zip:

- Either add the repo root to *Preferences → File Paths → Script Directories*,
- or symlink `open_sky` into your user extensions folder.

Then enable the add-on.

## Tests

```
blender -b --factory-startup --python tests/run_tests.py
```

The script exits with a non-zero status if any test fails. The tests cover:

- that every driver is valid and needs no Python;
- that the lamp colour matches the shader's transmittance;
- the time-of-day astronomy;
- presets, and upgrading old files;
- that a saved file works without the add-on;
- small renders in both engines.

Please run them before opening a pull request.

## Preview gallery

```
blender -b --factory-startup --python tools/render_previews.py
blender -b --factory-startup --python tools/render_previews.py -- SUNSET AURORA
```

## Building the zip

```
blender --command extension build --source-dir open_sky --output-dir dist
```

## Changing the shader

- **Group versions.** Node groups are rebuilt when their stored
  `os_version` differs from `GROUP_VERSION` in `sky.py`. Bump it whenever you
  change a group. Opening an older file then rebuilds the groups and restores
  every world's settings by input name (see `rig.upgrade_file`).
- **Renaming inputs.** Drivers and presets refer to inputs by name. If you
  rename one, update `rig.py`, `presets.py` and `ui.SECTIONS`.
- **Sun transmittance lives in two places.** It is computed in
  `sky.build_atmosphere` and in the lamp colour driver in `rig.py`. Keep the
  two in step; `lamp_matches_sky_transmittance` checks it.
- **Cloud dimming lives in two places.** It is computed in `sky.build_main`
  (`shade`) and in `rig.CLOUD_DIM` for the lamps. Keep the two in step.
- **No Python in drivers.** Driver expressions must stay *simple
  expressions* (`driver.is_simple_expression`), or files would need
  *Auto Run Python Scripts*.

## Releases

1. Bump `version` in `open_sky/blender_manifest.toml`.
2. Add an entry to `CHANGELOG.md`.
3. Build the zip and attach it to a GitHub release.
