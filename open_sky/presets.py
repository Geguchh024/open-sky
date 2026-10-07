# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in looks. Each preset starts from the defaults and overrides a few inputs.

`sun` is (elevation, azimuth) in degrees and is used when the sun is posed by
hand; `hour` and `day` (day of year, default 172) are used instead when Time of
Day is on. `moon` is the offset
(elevation, azimuth) in degrees from the point opposite the sun.
"""

import math

PRESETS = [
    ("CLEAR_DAY", "Clear Day", "Bright midday sky with a little haze", dict(
        sun=(55, 165), hour=12.5,
    )),
    ("MORNING", "Crisp Morning", "Low sun, cool clean air", dict(
        sun=(14, 100), hour=7.5,
        values={"Haze Density": 0.2, "Horizon Fog": 0.3},
    )),
    ("GOLDEN_HOUR", "Golden Hour", "Warm, low evening light", dict(
        sun=(6, 255), hour=18.7,
        values={"Haze Density": 0.5},
    )),
    ("SUNSET", "Sunset", "Sun on the horizon", dict(
        sun=(0.6, 268), hour=19.6,
        values={"Haze Density": 0.4, "Sun Glow": 0.5},
    )),
    ("BLUE_HOUR", "Blue Hour", "Just after sunset", dict(
        sun=(-4, 280), hour=20.1, moon=(0, 160),
    )),
    ("MOONLIT", "Moonlit Night", "Full moon over a starry sky", dict(
        sun=(-35, 330), hour=1.0, moon=(0, 10),
        values={"Star Density": 0.35, "Milky Way": 0.3, "Moon Glow": 0.8},
    )),
    ("STARRY", "Starry Night", "Moonless night with a bright Milky Way", dict(
        sun=(-40, 0), hour=0.0, moon=(-60, 170),
        values={"Star Density": 0.7, "Star Brightness": 1.5, "Milky Way": 1.5,
                "Haze Density": 0.15},
    )),
    # Aurora needs a dark sky: at 68 degrees north the June sun never sets,
    # so this one is set in winter.
    ("AURORA", "Aurora Night", "Northern lights at high latitude", dict(
        sun=(-30, 0), hour=23.0, day=15, moon=(-60, 170),
        values={"Aurora": 5.0, "Aurora Coverage": 0.75, "Latitude": 68.0, "Star Density": 0.6,
                "Milky Way": 0.5},
    )),
    ("HAZY", "Hazy Summer", "Milky, humid afternoon", dict(
        sun=(40, 220), hour=15.5,
        values={"Haze Density": 1.6, "Horizon Fog": 0.6, "Haze Anisotropy": 0.82},
    )),
    ("FOG", "Foggy Morning", "Thick ground fog with a soft sun", dict(
        sun=(10, 110), hour=8.0,
        values={"Haze Density": 1.2, "Horizon Fog": 4.0, "Sun Glow": 1.0},
    )),
    ("DUST", "Desert Dust", "Dusty air that turns the sky beige", dict(
        sun=(30, 200), hour=15.0,
        values={"Haze Density": 3.0, "Haze Color": (1.0, 0.72, 0.42),
                "Horizon Fog": 1.0, "Ground Color": (0.45, 0.32, 0.2)},
    )),
    ("SMOKE", "Wildfire Smoke", "Orange sun through heavy smoke", dict(
        sun=(18, 230), hour=17.0,
        values={"Haze Density": 6.0, "Haze Color": (0.95, 0.55, 0.3),
                "Horizon Fog": 1.5, "Haze Anisotropy": 0.65},
    )),
    ("SMOG", "City Smog", "Brown, polluted air", dict(
        sun=(25, 210), hour=16.0,
        values={"Haze Density": 2.5, "Haze Color": (0.85, 0.78, 0.62),
                "Horizon Fog": 0.8},
    )),
    # -- clouds and weather -----------------------------------------------------
    ("FAIR_CLOUDS", "Fair Weather Clouds", "Small white cumulus in a blue sky", dict(
        sun=(50, 160), hour=11.0,
        values={"Cloud Coverage": 0.35, "Cloud Scale": 1.2, "Cloud Puffiness": 0.8},
    )),
    ("PARTLY_CLOUDY", "Partly Cloudy", "Big cumulus with gaps of blue", dict(
        sun=(40, 200), hour=14.5,
        values={"Cloud Coverage": 0.55, "Cloud Thickness": 1.8, "Cirrus": 0.3},
    )),
    ("OVERCAST", "Overcast", "Grey cloud deck, soft shadows", dict(
        sun=(40, 170), hour=12.5,
        values={"Cloud Coverage": 1.0, "Cloud Density": 2.5, "Cloud Thickness": 1.5,
                "Cloud Darkness": 0.3, "Haze Density": 0.8, "Horizon Fog": 0.5},
    )),
    ("RAIN", "Rainy Day", "Low dark clouds and steady rain", dict(
        sun=(35, 190), hour=13.5,
        values={"Cloud Coverage": 1.0, "Cloud Density": 3.0, "Cloud Height": 1.0,
                "Cloud Thickness": 1.8, "Cloud Darkness": 0.55, "Rain": 1.0,
                "Haze Density": 1.0, "Wind Speed": 4.0},
    )),
    ("STORM", "Thunderstorm", "Towering dark clouds, rain and lightning", dict(
        sun=(25, 230), hour=17.0,
        values={"Cloud Coverage": 0.92, "Cloud Density": 4.0, "Cloud Height": 1.0,
                "Cloud Thickness": 3.0, "Cloud Puffiness": 1.0, "Cloud Darkness": 0.85,
                "Rain": 1.0, "Lightning": 0.8, "Wind Speed": 12.0, "Haze Density": 1.2},
    )),
    ("SNOW", "Snowfall", "Quiet snowfall under a bright grey sky", dict(
        sun=(20, 180), hour=12.0, day=15,
        values={"Cloud Coverage": 1.0, "Cloud Density": 2.0, "Cloud Darkness": 0.2,
                "Cloud Color": (0.95, 0.97, 1.0), "Snow": 1.0, "Wind Speed": 2.0,
                "Ground Color": (0.8, 0.82, 0.85)},
    )),
    ("BLIZZARD", "Blizzard", "Wind-driven snow, almost no visibility", dict(
        sun=(15, 180), hour=12.0, day=15,
        values={"Cloud Coverage": 1.0, "Cloud Density": 3.0, "Cloud Darkness": 0.35,
                "Snow": 1.0, "Wind Speed": 18.0, "Horizon Fog": 4.0,
                "Ground Color": (0.8, 0.82, 0.85)},
    )),
    ("CIRRUS", "Cirrus & Halo", "High ice clouds with a 22 degree halo", dict(
        sun=(35, 170), hour=12.0,
        values={"Cirrus": 0.8, "Ice Halo": 1.0, "Haze Density": 0.25},
    )),
    ("RAINBOW", "After the Rain", "Clearing shower with a rainbow", dict(
        sun=(20, 260), hour=17.5,
        values={"Cloud Coverage": 0.45, "Cloud Darkness": 0.3, "Rainbow": 1.0,
                "Rain": 0.15, "Haze Density": 0.4},
    )),
    ("SUNSET_CLOUDS", "Cloudy Sunset", "Clouds lit pink and orange from below", dict(
        sun=(0.5, 268), hour=19.6,
        values={"Cloud Coverage": 0.45, "Cirrus": 0.4, "Haze Density": 0.4},
    )),
]

PRESET_BY_ID = {p[0]: p for p in PRESETS}


def items(_self=None, _context=None):
    return [(pid, label, desc) for pid, label, desc, _ in PRESETS]


def converted(values):
    """Degrees -> radians for angle inputs, RGB -> RGBA for colours."""
    from . import sky

    out = {}
    for name, v in values.items():
        spec = sky.INPUT_SPECS[name]
        if len(spec) > 5 and spec[5] == "ANGLE":
            v = math.radians(v)
        if spec[1] == "color" and len(v) == 3:
            v = (*v, 1.0)
        out[name] = v
    return out
