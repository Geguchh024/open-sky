# SPDX-License-Identifier: GPL-3.0-or-later
"""The Open Sky world shader, built as shader node groups.

Everything here is plain Blender nodes, so a saved file renders the sky in
Cycles and EEVEE without the add-on installed.

Atmosphere model (single scattering with a cheap multiple-scattering term):

    ext   = Rayleigh * air + Ozone * ozone + 0.1 * haze * (2 - haze_colour)
    T(e)  = exp(-ext * airmass(e))        airmass(e) = 1 / (e + 0.05 exp(-14 e))
    sky   = E * T_sun_mid * (bR pR(mu) + bM pM(mu) + iso) / ext * (1 - T_view)

The same transmittance formula drives the sun lamp colour (see rig.py) so
the lamp always matches the sky.
"""

import math

import bpy

from . import clouds
from .nodekit import auto_layout, find_output, group_node, new_group

GROUP_VERSION = 2

MAIN = "Open Sky"
ATMOS = "OS Atmosphere"
MOON = "OS Moon"
STARS = "OS Stars"
MILKY = "OS Milky Way"
AURORA = "OS Aurora"
AURORA_LAYER = "OS Aurora Layer"
CLOUD_SLICE = "OS Cloud Slice"
CLOUDS = "OS Clouds"
CIRRUS = "OS Cirrus"
FX = "OS Sky FX"
ALL_GROUPS = (AURORA_LAYER, AURORA, MILKY, STARS, MOON, ATMOS,
              CLOUD_SLICE, CLOUDS, CIRRUS, FX, MAIN)

# Zenith optical depths per RGB channel.
RAYLEIGH = (0.05, 0.12, 0.28)
OZONE = (0.006, 0.016, 0.0008)
MIE = 0.1
FOG = 0.15
SKY_GAIN = 0.35
# airmass(e) = 1 / (e + A exp(-B e)); about 20 at the horizon.
AIRMASS_A = 0.05
AIRMASS_B = 14.0

# Equatorial unit vectors (J2000) of the galactic north pole and centre.
def _radec(ra, dec):
    ra, dec = math.radians(ra), math.radians(dec)
    return (math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec))


GALACTIC_POLE = _radec(192.86, 27.13)
GALACTIC_CENTRE = _radec(266.40, -28.94)

AURORA_LAYERS = 10

# -- interface of the main group ------------------------------------------------
# (name, kind, default, min, max[, subtype]); ANGLE defaults are in degrees.

MAIN_INPUTS = [
    ("panel", "Sun", [
        ("Sun Direction", "vector", (0.0, -0.5, 0.866)),
        ("Sun Strength", "float", 4.0, 0.0, 1000.0),
        ("Sun Temperature", "float", 6500.0, 800.0, 20000.0),
        ("Sun Tint", "color", (1.0, 1.0, 1.0)),
        ("Sun Size", "float", 0.545, 0.05, 20.0, "ANGLE"),
        ("Sun Disc", "float", 1.0, 0.0, 10.0),
        ("Sun Glow", "float", 0.3, 0.0, 10.0),
    ]),
    ("panel", "Atmosphere", [
        ("Sky Brightness", "float", 1.0, 0.0, 10.0),
        ("Air Density", "float", 1.0, 0.0, 10.0),
        ("Ozone", "float", 1.0, 0.0, 10.0),
        ("Haze Density", "float", 0.3, 0.0, 30.0),
        ("Haze Color", "color", (1.0, 1.0, 1.0)),
        ("Haze Anisotropy", "float", 0.76, 0.0, 0.98, "FACTOR"),
        ("Horizon Fog", "float", 0.0, 0.0, 20.0),
        ("Multiple Scattering", "float", 1.0, 0.0, 5.0),
        ("Ground Color", "color", (0.20, 0.18, 0.15)),
        ("Ground", "float", 1.0, 0.0, 1.0, "FACTOR"),
    ]),
    ("panel", "Night", [
        ("Night Color", "color", (0.012, 0.022, 0.06)),
        ("Night Brightness", "float", 0.15, 0.0, 10.0),
        ("Star Density", "float", 0.5, 0.0, 1.0, "FACTOR"),
        ("Star Brightness", "float", 1.0, 0.0, 100.0),
        ("Star Size", "float", 1.0, 0.1, 10.0),
        ("Star Colors", "float", 0.6, 0.0, 1.0, "FACTOR"),
        ("Twinkle", "float", 0.0, 0.0, 1.0, "FACTOR"),
        ("Milky Way", "float", 0.6, 0.0, 20.0),
        ("Milky Way Width", "float", 1.0, 0.1, 5.0),
        ("Dust Lanes", "float", 1.0, 0.0, 1.0, "FACTOR"),
        ("Latitude", "float", 45.0, -90.0, 90.0, "ANGLE"),
        ("Sky Rotation", "float", 0.0, -100000.0, 100000.0, "ANGLE"),
        ("Show Pole", "float", 0.0, 0.0, 1.0, "FACTOR"),
    ]),
    ("panel", "Moon", [
        ("Moon Direction", "vector", (0.0, 0.5, -0.866)),
        ("Moon Size", "float", 1.0, 0.05, 30.0, "ANGLE"),
        ("Moon Brightness", "float", 1.0, 0.0, 100.0),
        ("Moon Color", "color", (1.0, 0.96, 0.9)),
        ("Moon Detail", "float", 1.0, 0.0, 1.0, "FACTOR"),
        ("Moon Glow", "float", 0.5, 0.0, 10.0),
        ("Earthshine", "float", 0.15, 0.0, 1.0, "FACTOR"),
        ("Moon Light", "float", 0.1, 0.0, 100.0),
    ]),
    ("panel", "Aurora", [
        ("Aurora", "float", 0.0, 0.0, 50.0),
        ("Aurora Low Color", "color", (0.05, 1.0, 0.25)),
        ("Aurora High Color", "color", (0.35, 0.08, 1.0)),
        ("Aurora Height", "float", 1.0, 0.1, 10.0),
        ("Aurora Thickness", "float", 1.5, 0.0, 5.0),
        ("Aurora Scale", "float", 1.0, 0.05, 20.0),
        ("Aurora Waviness", "float", 1.0, 0.0, 5.0),
        ("Aurora Coverage", "float", 0.6, 0.0, 1.0, "FACTOR"),
        ("Aurora Speed", "float", 1.0, 0.0, 50.0),
        ("Aurora Rotation", "float", 0.0, -360.0, 360.0, "ANGLE"),
    ]),
    ("panel", "Clouds", [
        ("Cloud Coverage", "float", 0.0, 0.0, 1.0, "FACTOR"),
        ("Cloud Density", "float", 1.5, 0.0, 50.0),
        ("Cloud Height", "float", 1.5, 0.05, 50.0),
        ("Cloud Thickness", "float", 1.2, 0.0, 20.0),
        ("Cloud Scale", "float", 1.0, 0.01, 20.0),
        ("Cloud Puffiness", "float", 0.6, 0.0, 2.0),
        ("Cloud Darkness", "float", 0.0, 0.0, 1.0, "FACTOR"),
        ("Cloud Color", "color", (1.0, 1.0, 1.0)),
        ("Cloud Evolution", "float", 0.3, 0.0, 100.0),
        ("Cloud Distance", "float", 40.0, 1.0, 1000.0),
        ("Cloud Shadow", "float", 1.0, 0.0, 1.0, "FACTOR"),
        ("Cirrus", "float", 0.0, 0.0, 1.0, "FACTOR"),
        ("Cirrus Height", "float", 8.0, 0.1, 50.0),
        ("Cirrus Scale", "float", 1.0, 0.01, 20.0),
    ]),
    ("panel", "Weather", [
        ("Wind Speed", "float", 5.0, 0.0, 100.0),
        ("Wind Direction", "float", 45.0, -360.0, 360.0, "ANGLE"),
        ("Rain", "float", 0.0, 0.0, 1.0, "FACTOR"),
        ("Snow", "float", 0.0, 0.0, 1.0, "FACTOR"),
        ("Lightning", "float", 0.0, 0.0, 10.0),
        ("Rainbow", "float", 0.0, 0.0, 10.0),
        ("Ice Halo", "float", 0.0, 0.0, 10.0),
        ("Light Shafts", "float", 0.3, 0.0, 10.0),
    ]),
    ("Time", "float", 0.0, -1e6, 1e6),
]


def _flat(specs):
    for s in specs:
        if s[0] == "panel":
            yield from _flat(s[2])
        else:
            yield s


INPUT_SPECS = {s[0]: s for s in _flat(MAIN_INPUTS)}
# Inputs the rig drives; the UI shows them as read-only information.
DRIVEN_INPUTS = {"Sun Direction", "Moon Direction", "Time"}


def default_value(name):
    """Default of a main-group input in socket units (radians for angles)."""
    spec = INPUT_SPECS[name]
    v = spec[2]
    if len(spec) > 5 and spec[5] == "ANGLE":
        return math.radians(v)
    return v


# -- helpers ------------------------------------------------------------------------

def _airmass(nb, e):
    """Relative optical path length for a (clamped) elevation sine."""
    e = nb.max(e, 0.0)
    return nb.div(1.0, nb.add(e, nb.mul(AIRMASS_A, nb.exp(nb.mul(e, -AIRMASS_B)))))


def _extinction(nb, air, haze, haze_col):
    """Extinction of the lower atmosphere (air and haze), without ozone."""
    absorb = nb.vsub((2.0, 2.0, 2.0), haze_col)
    return nb.vadd(nb.vscale(RAYLEIGH, air), nb.vscale(absorb, nb.mul(haze, MIE)))


# -- atmosphere -----------------------------------------------------------------------

def build_atmosphere():
    ng, nb, gin, gout = new_group(ATMOS, [
        ("View", "vector", (0, 0, 1)),
        ("Sun", "vector", (0, 0, 1)),
        ("Sun Light", "color", (1, 1, 1)),
        ("Air Density", "float", 1.0, 0, 10),
        ("Ozone", "float", 1.0, 0, 10),
        ("Haze Density", "float", 0.3, 0, 30),
        ("Haze Color", "color", (1, 1, 1)),
        ("Haze Anisotropy", "float", 0.76, 0, 0.98),
        ("Horizon Fog", "float", 0.0, 0, 20),
        ("Multiple Scattering", "float", 1.0, 0, 5),
        ("Ground Color", "color", (0.2, 0.18, 0.15)),
        ("Ground", "float", 1.0, 0, 1),
    ], [("Sky", "color"), ("View Transmittance", "color"),
        ("Sun Transmittance", "color"), ("Day", "float")], GROUP_VERSION)
    g = gin.outputs
    view, sun = g["View"], g["Sun"]
    _, _, hv = nb.sep(view)
    _, _, hs = nb.sep(sun)

    haze_col = g["Haze Color"]
    ext_low = _extinction(nb, g["Air Density"], g["Haze Density"], haze_col)
    ozone = nb.vscale(OZONE, g["Ozone"])
    ext_sun = nb.vadd(ext_low, ozone)
    fog = nb.mul(g["Horizon Fog"], FOG)
    ext_view = nb.vadd(ext_sun, nb.vscale(nb.vsub((2.0, 2.0, 2.0), haze_col), fog))

    # Below the horizon the ground is close, so the path through the air is
    # much shorter; blend that in smoothly to avoid a seam at the horizon.
    below = nb.mul(nb.smooth(hv, 0.0, -0.03), g["Ground"])
    path = nb.lerp(1.0, 0.25, below)
    m_view = nb.mul(_airmass(nb, nb.abs(hv)), path)
    m_sun = _airmass(nb, hs)

    t_view = nb.vexp(nb.vscale(ext_view, nb.mul(m_view, -1.0)))
    t_sun = nb.vexp(nb.vscale(ext_sun, nb.mul(m_sun, -1.0)))
    # Sunlight reaching the scattering points. Looking up, those points are
    # high in thin air, so the sun's path through the dense layer is shorter;
    # ozone sits above everything and always takes the full path, which keeps
    # the twilight zenith blue.
    reach = nb.lerp(0.5, 0.12, nb.clamp01(hv))
    mid = nb.vadd(nb.vscale(ext_low, nb.mul(m_sun, reach)), nb.vscale(ozone, m_sun))
    t_sun_mid = nb.vexp(nb.vscale(mid, -1.0))

    # Phase functions.
    mu = nb.dot(view, sun)
    p_ray = nb.mul(3.0 / (16.0 * math.pi), nb.add(1.0, nb.mul(mu, mu)))
    gg = g["Haze Anisotropy"]
    g2 = nb.mul(gg, gg)
    denom = nb.sub(nb.add(1.0, g2), nb.mul(nb.mul(gg, 2.0), mu))
    p_mie = nb.div(nb.sub(1.0, g2), nb.mul(4.0 * math.pi, nb.pow(nb.max(denom, 1e-4), 1.5)))

    b_ray = nb.vscale(RAYLEIGH, g["Air Density"])
    b_mie = nb.vscale(haze_col, nb.add(nb.mul(g["Haze Density"], MIE), fog))
    scat = nb.vadd(nb.vscale(b_ray, p_ray), nb.vscale(b_mie, p_mie))
    iso = nb.vscale(nb.vadd(b_ray, b_mie), nb.mul(g["Multiple Scattering"], 0.3 / (4.0 * math.pi)))
    albedo = nb.vdiv(nb.vadd(scat, iso), ext_view)

    # Earth's shadow: the sky keeps some light through civil twilight.
    day = nb.smooth(hs, -0.12, 0.03)
    light = nb.vscale(nb.vmul(g["Sun Light"], t_sun_mid), nb.mul(day, 4.0 * math.pi * SKY_GAIN))
    inscatter = nb.vmul(nb.vmul(light, albedo), nb.vsub((1.0, 1.0, 1.0), t_view))

    # Lit ground seen through the air in front of it.
    sun_up = nb.max(hs, 0.0)
    ground_irr = nb.vadd(nb.vscale(t_sun, sun_up), nb.vscale(t_sun_mid, nb.mul(day, 0.2)))
    ground = nb.vmul(nb.vmul(g["Ground Color"], nb.vmul(g["Sun Light"], ground_irr)), t_view)
    ground = nb.vscale(ground, nb.mul(below, 1.0 / math.pi))

    nb.link(nb.vadd(inscatter, ground), gout.inputs["Sky"])
    nb.link(t_view, gout.inputs["View Transmittance"])
    nb.link(t_sun, gout.inputs["Sun Transmittance"])
    nb.link(day, gout.inputs["Day"])
    auto_layout(ng)
    return ng


# -- moon ---------------------------------------------------------------------------------

def build_moon():
    ng, nb, gin, gout = new_group(MOON, [
        ("View", "vector", (0, 0, 1)),
        ("Moon", "vector", (0, 0, 1)),
        ("Sun", "vector", (0, 0, -1)),
        ("Size", "float", 1.0, 0.05, 30, "ANGLE"),
        ("Brightness", "float", 1.0, 0, 100),
        ("Color", "color", (1, 1, 1)),
        ("Detail", "float", 1.0, 0, 1),
        ("Glow", "float", 0.5, 0, 10),
        ("Earthshine", "float", 0.15, 0, 1),
    ], [("Color", "color"), ("Mask", "float"), ("Phase", "float")], GROUP_VERSION)
    g = gin.outputs
    view, moon, sun = g["View"], g["Moon"], g["Sun"]
    radius = nb.mul(g["Size"], 0.5)
    offset = nb.vsub(view, moon)
    chord = nb.length(offset)
    x = nb.div(chord, radius)
    inside = nb.smooth(x, 1.0, 0.96)

    # Reconstruct the sphere normal facing the viewer, light it by the sun.
    p = nb.vscale(offset, nb.div(1.0, radius))
    zc = nb.sqrt(nb.max(nb.sub(1.0, nb.dot(p, p)), 0.0))
    normal = nb.vsub(p, nb.vscale(moon, zc))
    ndl = nb.dot(normal, sun)
    lit = nb.lerp(nb.smooth(ndl, -0.04, 0.12), nb.clamp01(ndl), 0.3)

    # Surface coordinates fixed to the moon so the texture doesn't swim.
    t1 = nb.normalize(nb.cross(moon, (0.0, 0.0, 1.0)))
    t2 = nb.cross(t1, moon)
    coords = nb.comb(nb.dot(normal, t1), nb.dot(normal, t2), nb.dot(normal, moon))
    maria = nb.smooth(nb.nfac(coords, 1.3, 4.0, 0.55), 0.5, 0.62)
    craters = nb.voronoi(coords, 6.0).outputs["Distance"]
    rim = nb.mul(nb.smooth(craters, 0.22, 0.3), nb.smooth(craters, 0.38, 0.3))
    grain = nb.nfac(coords, 18.0, 3.0, 0.6)
    tex = nb.mul(nb.sub(1.0, nb.mul(maria, 0.45)), nb.add(0.8, nb.mul(grain, 0.35)))
    tex = nb.add(tex, nb.mul(rim, 0.12))
    albedo = nb.vscale(g["Color"], nb.lerp(1.0, tex, g["Detail"]))

    shade = nb.add(lit, nb.mul(nb.mul(g["Earthshine"], 0.05), nb.one_minus(lit)))
    disc = nb.vscale(albedo, nb.mul(nb.mul(shade, inside), nb.mul(g["Brightness"], 0.8)))

    phase = nb.mul(nb.sub(1.0, nb.dot(moon, sun)), 0.5)
    halo = nb.add(nb.mul(nb.exp(nb.div(chord, -0.05)), 0.12),
                  nb.mul(nb.exp(nb.div(chord, -0.3)), 0.015))
    glow = nb.vscale(g["Color"], nb.mul(nb.mul(halo, phase), nb.mul(g["Glow"], g["Brightness"])))

    nb.link(nb.vadd(disc, glow), gout.inputs["Color"])
    nb.link(inside, gout.inputs["Mask"])
    nb.link(phase, gout.inputs["Phase"])
    auto_layout(ng)
    return ng


# -- stars and the Milky Way ---------------------------------------------------------

STAR_LAYERS = (  # (cells per radian, relative brightness)
    (70.0, 1.0),
    (170.0, 0.5),
)


def build_stars():
    ng, nb, gin, gout = new_group(STARS, [
        ("Vector", "vector", (0, 0, 1)),
        ("Density", "float", 0.5, 0, 1),
        ("Brightness", "float", 1.0, 0, 100),
        ("Size", "float", 1.0, 0.1, 10),
        ("Colors", "float", 0.6, 0, 1),
        ("Twinkle", "float", 0.0, 0, 1),
        ("Time", "float", 0.0, -1e6, 1e6),
    ], [("Color", "color")], GROUP_VERSION)
    g = gin.outputs
    total = None
    for i, (scale, gain) in enumerate(STAR_LAYERS):
        vor = nb.voronoi(g["Vector"], scale)
        r, gch, b = nb.sep(vor.outputs["Color"])
        exists = nb.math("LESS_THAN", r, g["Density"])
        mag = nb.add(nb.mul(nb.pow(gch, 6.0), 4.0), 0.06)
        radius = nb.mul(g["Size"], 0.0008 * scale)
        d = nb.div(vor.outputs["Distance"], radius)
        spot = nb.exp(nb.mul(nb.mul(d, d), -1.0))
        twinkle = nb.nfac(vor.outputs["Position"], 3.0, 1.0, dims="4D",
                          w=nb.add(nb.mul(g["Time"], 3.0), i * 17.0))
        twinkle = nb.sub(1.0, nb.mul(g["Twinkle"], nb.smooth(twinkle, 0.3, 0.75)))
        value = nb.mul(nb.mul(spot, exists), nb.mul(nb.mul(mag, twinkle), gain))
        colour = nb.mix((1.0, 1.0, 1.0), nb.blackbody(nb.add(2800.0, nb.mul(b, 9000.0))),
                        g["Colors"])
        layer = nb.vscale(colour, value)
        total = layer if total is None else nb.vadd(total, layer)
    nb.link(nb.vscale(total, g["Brightness"]), gout.inputs["Color"])
    auto_layout(ng)
    return ng


def build_milky_way():
    ng, nb, gin, gout = new_group(MILKY, [
        ("Vector", "vector", (0, 0, 1)),
        ("Strength", "float", 0.6, 0, 20),
        ("Width", "float", 1.0, 0.1, 5),
        ("Dust Lanes", "float", 1.0, 0, 1),
    ], [("Color", "color")], GROUP_VERSION)
    g = gin.outputs
    v = g["Vector"]
    width = nb.mul(g["Width"], 0.13)
    lat = nb.div(nb.dot(v, GALACTIC_POLE), width)
    band = nb.exp(nb.mul(nb.mul(lat, lat), -1.0))
    to_core = nb.vsub(v, GALACTIC_CENTRE)
    core = nb.exp(nb.div(nb.dot(to_core, to_core), -0.25))

    clouds = nb.remap(nb.nfac(v, 4.0, 8.0, 0.6, 0.2), 0.3, 0.75, 0.15, 1.0)
    dust = nb.smooth(nb.nfac(v, 7.0, 6.0, 0.55, 0.4), 0.5, 0.62)
    thin = nb.div(lat, 0.45)
    dust = nb.mul(dust, nb.exp(nb.mul(nb.mul(thin, thin), -1.0)))
    grain = nb.remap(nb.nfac(v, 90.0, 2.0), 0.45, 0.7, 0.7, 1.3)

    value = nb.mul(band, nb.add(0.35, nb.mul(core, 2.0)))
    value = nb.mul(nb.mul(value, clouds), grain)
    value = nb.mul(value, nb.sub(1.0, nb.mul(nb.mul(dust, g["Dust Lanes"]), 0.85)))
    colour = nb.mix((0.62, 0.7, 1.0), (1.0, 0.75, 0.48), nb.clamp01(nb.mul(core, 1.3)))
    nb.link(nb.vscale(colour, nb.mul(value, nb.mul(g["Strength"], 0.05))), gout.inputs["Color"])
    auto_layout(ng)
    return ng


# -- aurora --------------------------------------------------------------------------------

def build_aurora_layer():
    """Curtain density where the view ray crosses one altitude slice."""
    ng, nb, gin, gout = new_group(AURORA_LAYER, [
        ("Vector", "vector", (0, 0, 1)),
        ("Altitude", "float", 1.0, 0, 100),
        ("Scale", "float", 1.0, 0.05, 20),
        ("Waviness", "float", 1.0, 0, 5),
        ("Coverage", "float", 0.6, 0, 1),
        ("Time", "float", 0.0, -1e6, 1e6),
    ], [("Fac", "float")], GROUP_VERSION)
    g = gin.outputs
    vx, vy, vz = nb.sep(g["Vector"])
    t = nb.div(g["Altitude"], nb.max(vz, 0.035))
    sc = g["Scale"]
    x = nb.mul(nb.mul(vx, t), sc)
    y = nb.mul(nb.mul(vy, t), sc)
    time = g["Time"]

    # Curtains are the ridges of a noise field stretched along X (east-west
    # arcs), bent by a slower noise.
    warp = nb.nfac(nb.comb(nb.mul(x, 0.04), nb.mul(y, 0.04), nb.mul(time, 0.02)), 1.0, 2.0)
    y_w = nb.add(y, nb.mul(nb.sub(warp, 0.5), nb.mul(g["Waviness"], 12.0)))
    n = nb.nfac(nb.comb(nb.mul(x, 0.03), nb.mul(y_w, 0.2), nb.mul(time, 0.03)), 1.0, 2.0, 0.4)
    ridge = nb.pow(nb.sub(1.0, nb.mul(nb.abs(nb.sub(n, 0.5)), 2.0)), 14.0)

    cov = nb.nfac(nb.comb(nb.mul(x, 0.025), nb.mul(y, 0.025), nb.mul(time, 0.01)), 1.0, 1.0)
    lo = nb.sub(1.0, g["Coverage"])
    cover = nb.smooth(cov, nb.sub(lo, 0.05), nb.add(lo, 0.1))
    # Vertical rays: they only vary along the curtain, so they stay upright.
    rays = nb.nfac(nb.comb(nb.mul(x, 0.6), nb.mul(y_w, 0.05), nb.mul(time, 0.15)), 1.0, 2.0)
    rays = nb.add(0.35, nb.mul(nb.smooth(rays, 0.35, 0.7), 0.65))
    nb.link(nb.mul(nb.mul(ridge, cover), rays), gout.inputs["Fac"])
    auto_layout(ng)
    return ng


def build_aurora(layer_group):
    ng, nb, gin, gout = new_group(AURORA, [
        ("Vector", "vector", (0, 0, 1)),
        ("Strength", "float", 0.0, 0, 50),
        ("Low Color", "color", (0.05, 1.0, 0.25)),
        ("High Color", "color", (0.35, 0.08, 1.0)),
        ("Height", "float", 1.0, 0.1, 10),
        ("Thickness", "float", 1.5, 0, 5),
        ("Scale", "float", 1.0, 0.05, 20),
        ("Waviness", "float", 1.0, 0, 5),
        ("Coverage", "float", 0.6, 0, 1),
        ("Speed", "float", 1.0, 0, 50),
        ("Rotation", "float", 0.0, -360, 360, "ANGLE"),
        ("Time", "float", 0.0, -1e6, 1e6),
    ], [("Color", "color")], GROUP_VERSION)
    g = gin.outputs
    v = nb.rotate(g["Vector"], "Z", g["Rotation"])
    time = nb.mul(g["Time"], g["Speed"])
    # Each render sample sees the slices at slightly different heights (the
    # view vector jitters inside the pixel), so they add up to a continuous
    # curtain instead of visible stripes.
    jitter = nb.node("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
    nb.set(jitter, "Vector", nb.vscale(g["Vector"], 4000.0))
    jitter = jitter.outputs["Value"]
    total = None
    for i in range(AURORA_LAYERS):
        frac = nb.div(nb.add(jitter, float(i)), float(AURORA_LAYERS))
        layer = group_node(nb, layer_group)
        nb.set(layer, "Vector", v)
        nb.set(layer, "Altitude", nb.mul(g["Height"], nb.add(1.0, nb.mul(g["Thickness"], frac))))
        for key in ("Scale", "Waviness", "Coverage"):
            nb.set(layer, key, g[key])
        nb.set(layer, "Time", time)
        # Bright, sharp lower edge fading out towards the top of the curtain.
        weight = nb.mul(nb.exp(nb.mul(frac, -2.5)), nb.smooth(frac, 0.0, 0.06))
        colour = nb.mix(g["Low Color"], g["High Color"], nb.pow(frac, 0.8))
        part = nb.vscale(colour, nb.mul(find_output(layer, "Fac"), weight))
        total = part if total is None else nb.vadd(total, part)
    _, _, vz = nb.sep(g["Vector"])
    fade = nb.smooth(vz, 0.0, 0.1)
    scale = nb.mul(nb.mul(g["Strength"], fade), 1.2 / AURORA_LAYERS)
    nb.link(nb.vscale(total, scale), gout.inputs["Color"])
    auto_layout(ng)
    return ng


# -- the main group ----------------------------------------------------------------------

def _wire(nb, node, gin, mapping):
    for dst, src in mapping.items():
        nb.set(node, dst, gin.outputs[src])


def build_main(groups):
    ng, nb, gin, gout = new_group(MAIN, MAIN_INPUTS, [
        ("Background", "shader"), ("Volume", "shader"), ("Color", "color"), ("Day", "float"),
    ], GROUP_VERSION)
    g = gin.outputs

    coords = nb.node("ShaderNodeTexCoord")
    view = nb.normalize(coords.outputs["Generated"])
    sun = nb.normalize(g["Sun Direction"])
    moon_dir = nb.normalize(g["Moon Direction"])
    _, _, vz = nb.sep(view)
    _, _, sz = nb.sep(sun)

    sun_light = nb.vscale(nb.vmul(nb.blackbody(g["Sun Temperature"]), g["Sun Tint"]),
                          g["Sun Strength"])

    # Rain and snow thicken the air near the ground.
    fog = nb.add(g["Horizon Fog"], nb.add(nb.mul(g["Rain"], 1.5), nb.mul(g["Snow"], 2.5)))

    def atmosphere(v, light_dir, light):
        node = group_node(nb, groups[ATMOS])
        nb.set(node, "View", v)
        nb.set(node, "Sun", light_dir)
        nb.set(node, "Sun Light", light)
        nb.set(node, "Horizon Fog", fog)
        _wire(nb, node, gin, {k: k for k in (
            "Air Density", "Ozone", "Haze Density", "Haze Color", "Haze Anisotropy",
            "Multiple Scattering", "Ground Color", "Ground")})
        return node

    # Light left under the clouds. `shade` uses the same formula that dims the
    # sun lamp (rig.py); the air below a deck still gets the diffuse light
    # coming through it, about a quarter of a clear day.
    cov2 = nb.mul(g["Cloud Coverage"], g["Cloud Coverage"])
    opaque = nb.one_minus(nb.exp(nb.mul(nb.mul(g["Cloud Density"], g["Cloud Thickness"]), -1.0)))
    shade = nb.mul(g["Cloud Shadow"], nb.mul(cov2, opaque))
    under = nb.mul(nb.sub(1.0, nb.mul(shade, 0.75)),
                   nb.sub(1.0, nb.mul(nb.mul(g["Cloud Shadow"], g["Cirrus"]), 0.2)))
    sun_under = nb.vscale(sun_light, under)

    atm = atmosphere(view, sun, sun_under)
    t_view = find_output(atm, "View Transmittance")
    t_sun = find_output(atm, "Sun Transmittance")
    sky = nb.vscale(find_output(atm, "Sky"), g["Sky Brightness"])

    # Sun disc with limb darkening, plus a soft glow. Camera rays only: the
    # sun lamp already lights the scene, and its specular highlight matches.
    radius = nb.mul(g["Sun Size"], 0.5)
    chord = nb.length(nb.vsub(view, sun))
    x = nb.div(chord, radius)
    mask = nb.mul(nb.smooth(x, 1.0, 0.97), nb.smooth(vz, -0.002, 0.001))
    limb = nb.sub(1.0, nb.mul(nb.sub(1.0, nb.sqrt(nb.max(nb.sub(1.0, nb.mul(x, x)), 0.0))), 0.6))
    solid = nb.mul(nb.mul(radius, radius), math.pi)
    disc = nb.mul(nb.div(nb.mul(mask, limb), solid), g["Sun Disc"])
    glow = nb.add(nb.mul(nb.exp(nb.div(chord, -0.02)), 0.05),
                  nb.mul(nb.exp(nb.div(chord, -0.15)), 0.008))
    glow = nb.mul(nb.mul(glow, g["Sun Glow"]), nb.smooth(vz, -0.05, 0.02))
    sun_seen = nb.vscale(nb.vmul(sun_light, t_sun), nb.add(disc, glow))
    camera = nb.node("ShaderNodeLightPath").outputs["Is Camera Ray"]
    sun_seen = nb.vscale(sun_seen, camera)

    # Celestial frame: tilt the pole up to the latitude, spin by sky rotation.
    tilt = nb.sub(math.pi / 2.0, g["Latitude"])
    eq = nb.rotate(nb.rotate(view, "X", tilt), "Z", g["Sky Rotation"], invert=True)

    moon = group_node(nb, groups[MOON])
    nb.set(moon, "View", view)
    nb.set(moon, "Moon", moon_dir)
    nb.set(moon, "Sun", sun)
    _wire(nb, moon, gin, {"Size": "Moon Size", "Brightness": "Moon Brightness",
                          "Color": "Moon Color", "Detail": "Moon Detail",
                          "Glow": "Moon Glow", "Earthshine": "Earthshine"})
    # Moonlight scattered by the same atmosphere.
    moon_light = nb.vscale(g["Moon Color"],
                           nb.mul(g["Moon Light"], find_output(moon, "Phase")))
    moon_atm = atmosphere(view, moon_dir, nb.vscale(moon_light, under))
    sky = nb.vadd(sky, nb.vscale(find_output(moon_atm, "Sky"), g["Sky Brightness"]))

    moon_vis = nb.smooth(vz, -0.004, 0.004)
    moon_col = nb.vscale(nb.vmul(find_output(moon, "Color"), t_view), moon_vis)

    stars = group_node(nb, groups[STARS])
    nb.set(stars, "Vector", eq)
    _wire(nb, stars, gin, {"Density": "Star Density", "Brightness": "Star Brightness",
                           "Size": "Star Size", "Colors": "Star Colors",
                           "Twinkle": "Twinkle", "Time": "Time"})
    milky = group_node(nb, groups[MILKY])
    nb.set(milky, "Vector", eq)
    _wire(nb, milky, gin, {"Strength": "Milky Way", "Width": "Milky Way Width",
                           "Dust Lanes": "Dust Lanes"})
    aurora = group_node(nb, groups[AURORA])
    nb.set(aurora, "Vector", view)
    _wire(nb, aurora, gin, {"Strength": "Aurora", "Low Color": "Aurora Low Color",
                            "High Color": "Aurora High Color", "Height": "Aurora Height",
                            "Thickness": "Aurora Thickness", "Scale": "Aurora Scale",
                            "Waviness": "Aurora Waviness", "Coverage": "Aurora Coverage",
                            "Speed": "Aurora Speed", "Rotation": "Aurora Rotation",
                            "Time": "Time"})

    # Night layers fade in through nautical twilight; the moon hides stars.
    dark = nb.smooth(sz, -0.02, -0.2)
    above = nb.smooth(vz, -0.002, 0.004)
    hidden = nb.one_minus(find_output(moon, "Mask"))
    deep = nb.vadd(nb.vscale(find_output(stars, "Color"), hidden), find_output(milky, "Color"))
    deep = nb.vadd(deep, find_output(aurora, "Color"))
    deep = nb.vscale(nb.vmul(deep, t_view), nb.mul(dark, above))

    airglow = nb.vscale(g["Night Color"],
                        nb.mul(g["Night Brightness"], nb.sub(1.0, nb.mul(nb.clamp01(vz), 0.4))))

    # Debug overlay: celestial pole, a 10 degree ring around it and the equator.
    _, _, pz = nb.sep(eq)
    pole = nb.add(nb.smooth(pz, 0.9994, 0.9999),
                  nb.smooth(nb.abs(nb.sub(pz, math.cos(math.radians(10.0)))), 0.0016, 0.0004))
    equator = nb.smooth(nb.abs(pz), 0.002, 0.0005)
    debug = nb.vadd(nb.vscale((1.0, 0.05, 0.02), pole), nb.vscale((0.0, 0.6, 1.0), equator))
    debug = nb.vscale(debug, nb.mul(g["Show Pole"], 2.0))

    # The sun disc is composited separately: it is so bright that ordinary
    # cloud transparency would let it shine through a closed deck.
    colour = nb.vadd(sky, nb.vadd(moon_col, deep))
    colour = nb.vadd(nb.vadd(colour, airglow), debug)

    # -- weather and clouds, composited over everything behind them ----------
    time = g["Time"]
    fx = group_node(nb, groups[FX])
    nb.set(fx, "View", view)
    nb.set(fx, "Sun", sun)
    nb.set(fx, "Sun Light", nb.vmul(sun_light, t_sun))
    nb.set(fx, "Time", time)
    _wire(nb, fx, gin, {"Rainbow": "Rainbow", "Halo": "Ice Halo",
                        "Lightning": "Lightning", "Cloud Height": "Cloud Height"})
    flash = find_output(fx, "Flash")

    # Clouds are lit by the sun (red from below at dusk) or, at night, the moon.
    _, _, mz = nb.sep(moon_dir)
    day_c = nb.smooth(sz, -0.15, 0.0)
    key_dir = nb.normalize(nb.vadd(nb.vscale(sun, day_c),
                                   nb.vscale(moon_dir, nb.one_minus(day_c))))
    night_c = nb.mul(nb.one_minus(day_c), nb.smooth(mz, -0.05, 0.05))
    key_light = nb.vadd(nb.vscale(nb.vmul(sun_light, t_sun), day_c),
                        nb.vscale(moon_light, nb.mul(night_c, 3.0)))
    zenith = atmosphere((0.0, 0.0, 1.0), sun, sun_light)
    # Under a closed deck the light filling the clouds is grey, not sky blue,
    # and dimmer: it has come through the deck.
    zen = nb.vscale(find_output(zenith, "Sky"),
                    nb.mul(g["Sky Brightness"], nb.sub(1.3, nb.mul(shade, 0.6))))
    grey = nb.mul(nb.luminance(zen), 1.2)
    zen = nb.mix(zen, nb.comb(grey, grey, grey), nb.mul(g["Cloud Coverage"], 0.85))
    ambient = nb.vadd(zen, nb.vscale(g["Night Color"], nb.mul(g["Night Brightness"], 2.0)))
    ambient = nb.vadd(ambient, nb.vscale(moon_light, nb.mul(night_c, 0.3)))

    wind_dir = g["Wind Direction"]
    wind = nb.comb(nb.math("SINE", wind_dir), nb.math("COSINE", wind_dir), 0.0)
    drift = nb.mul(nb.mul(g["Wind Speed"], time), -clouds.WIND_KM)

    cirrus = group_node(nb, groups[CIRRUS])
    nb.set(cirrus, "View", view)
    nb.set(cirrus, "Light Dir", key_dir)
    nb.set(cirrus, "Light Color", key_light)
    nb.set(cirrus, "Ambient", ambient)
    nb.set(cirrus, "Offset", nb.vscale(wind, nb.mul(drift, 2.0)))
    nb.set(cirrus, "Direction", wind_dir)
    _wire(nb, cirrus, gin, {"Coverage": "Cirrus", "Height": "Cirrus Height",
                            "Scale": "Cirrus Scale"})
    ci_fade = nb.smooth(vz, 0.0, 0.12)
    ci_alpha = nb.mul(find_output(cirrus, "Alpha"), ci_fade)
    colour = nb.vadd(nb.vscale(colour, nb.one_minus(ci_alpha)),
                     nb.vscale(find_output(cirrus, "Color"), ci_fade))
    colour = nb.vadd(colour, find_output(fx, "Halo"))

    deck = group_node(nb, groups[CLOUDS])
    nb.set(deck, "View", view)
    nb.set(deck, "Light Dir", key_dir)
    nb.set(deck, "Light Color", key_light)
    nb.set(deck, "Ambient", ambient)
    nb.set(deck, "Flash", flash)
    nb.set(deck, "Offset", nb.vscale(wind, drift))
    nb.set(deck, "Evolve", nb.mul(time, g["Cloud Evolution"]))
    _wire(nb, deck, gin, {"Coverage": "Cloud Coverage", "Density": "Cloud Density",
                          "Height": "Cloud Height", "Thickness": "Cloud Thickness",
                          "Scale": "Cloud Scale", "Puffiness": "Cloud Puffiness",
                          "Darkness": "Cloud Darkness", "Color": "Cloud Color"})
    # Distant clouds melt into the haze.
    fade = nb.exp(nb.div(nb.mul(find_output(deck, "Distance"), -1.0), g["Cloud Distance"]))
    cu_alpha = nb.mul(find_output(deck, "Alpha"), fade)
    colour = nb.vadd(nb.vscale(colour, nb.one_minus(cu_alpha)),
                     nb.vscale(find_output(deck, "Color"), fade))

    clear = nb.mul(nb.one_minus(ci_alpha), nb.pow(nb.one_minus(cu_alpha), 10.0))
    colour = nb.vadd(colour, nb.vscale(sun_seen, clear))
    colour = nb.vadd(colour, nb.vadd(find_output(fx, "Rainbow"), find_output(fx, "Bolt")))
    colour = nb.vadd(colour, nb.vscale(flash, nb.mul(nb.smooth(vz, -0.05, 0.1), 0.01)))

    # Light shafts: a thin world volume the sun lamp shines through. It is only
    # connected to the World Output when the Light Shafts option is on.
    shafts = nb.node("ShaderNodeVolumePrincipled")
    nb.set(shafts, "Density", nb.mul(g["Light Shafts"], 0.01))
    nb.set(shafts, "Anisotropy", 0.6)
    nb.link(shafts.outputs[0], gout.inputs["Volume"])

    bg = nb.node("ShaderNodeBackground")
    nb.set(bg, "Color", colour)
    nb.set(bg, "Strength", 1.0)
    nb.link(bg.outputs[0], gout.inputs["Background"])
    nb.link(colour, gout.inputs["Color"])
    nb.link(find_output(atm, "Day"), gout.inputs["Day"])
    auto_layout(ng)
    return ng


def groups_current():
    return all(
        (ng := bpy.data.node_groups.get(name)) is not None
        and ng.get("os_version") == GROUP_VERSION and len(ng.nodes) > 2
        for name in ALL_GROUPS
    )


def ensure_groups(force=False):
    """Build every group if missing or outdated. Returns the main group."""
    if not force and groups_current():
        return bpy.data.node_groups[MAIN]
    groups = {}
    groups[ATMOS] = build_atmosphere()
    groups[MOON] = build_moon()
    groups[STARS] = build_stars()
    groups[MILKY] = build_milky_way()
    groups[AURORA] = build_aurora(build_aurora_layer())
    cloud_slice = clouds.build_cloud_slice(GROUP_VERSION)
    groups[CLOUDS] = clouds.build_clouds(cloud_slice, GROUP_VERSION)
    groups[CIRRUS] = clouds.build_cirrus(GROUP_VERSION)
    groups[FX] = clouds.build_fx(GROUP_VERSION)
    for ng in (cloud_slice, groups[CLOUDS], groups[CIRRUS], groups[FX]):
        auto_layout(ng)
    return build_main(groups)
