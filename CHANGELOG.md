# Changelog

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
