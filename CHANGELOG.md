# Changelog

## 0.2.2

- Much faster viewport, still or moving. Layers that are switched off
  (cloud deck, cirrus, aurora, rainbow/halo/lightning) are now cut out of
  the shader instead of being computed at strength 0: a clear sky draws
  about 8x faster (130 ms to 15 ms per frame at 1080p on an RTX 5060). A layer
  comes back by itself when its strength goes above 0 or is keyframed.
- Draft Clouds (Clouds panel): half the cloud slices and less noise detail,
  about twice as fast in the viewport. Turn it off for final renders; with it
  off the clouds render exactly as before.

## 0.2.1

- Much faster animation playback (about 3-4 fps to 20-24 fps in the EEVEE
  viewport). The sky's clock is now a scene property (`os_time`) read by an
  Attribute node, so moving clouds, stars and aurora no longer re-bake the
  world lighting or update the lamps and their shadows every frame. Renders
  are unchanged, and files from 0.2.0 are converted when opened.
- Camera & Tools has a Sky Lighting resolution setting (EEVEE). 256 makes
  animating the sun about twice as fast.

## 0.2.0

- Clouds:
  - A cumulus/stratus deck, from fair-weather cumulus to overcast and storm
    clouds, lit by the sun and moon.
  - High cirrus.
  - Clouds drift with the wind, hide the sun, and dim and soften the sun lamp.
- Weather:
  - Geometry Nodes rain and snow that follow the camera and blow with the wind.
  - Lightning that lights the clouds.
  - A rainbow and a 22° ice halo.
  - Optional light shafts.
- 11 new presets, from Fair Weather Clouds to Thunderstorm, Snowfall and
  Blizzard.
- Fixed: with Time of Day on, Aurora Night showed daylight. The preset was set
  at 68°N in June, when the sun never sets; it now uses a winter date. The
  panel also warns about midnight sun and polar night.
- The preset dropdown now shows the preset that was applied.
- Sky files made with 0.1.0 are upgraded automatically, keeping their
  settings.

## 0.1.0

- First release:
  - A procedural world shader for Cycles and EEVEE: an atmosphere with
    haze and fog, a sun disc and glow, a moon with phases and earthshine,
    stars, the Milky Way and an animated aurora.
  - Sun and moon lamps kept in sync with the sky by Python-free drivers.
  - Time of Day mode (hour, day of year, latitude) with matching star rotation.
  - Automatic night exposure.
  - 13 presets.
