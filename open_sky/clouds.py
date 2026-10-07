# SPDX-License-Identifier: GPL-3.0-or-later
"""Clouds and sky effects for the Open Sky world shader.

Clouds are drawn in the world shader, not as volume objects, so they stay
fast in EEVEE and Cycles. The cloud deck is a slab between a base and a top
height; the view ray is sampled at CLOUD_SLICES heights inside it (jittered
per render sample) and composited front to back, which reads like a
volume. Each sample also looks a short way towards the light for
self-shadowing. Units are kilometres, so the wind in m/s moves clouds at a
believable speed.
"""

import math

from .nodekit import find_output, group_node, new_group

CLOUD_SLICES = 8
WIND_KM = 0.001  # m/s -> km/s


def _hg(nb, mu, g):
    """Henyey-Greenstein phase function scaled so isotropic scattering is 1."""
    g2 = g * g
    denom = nb.pow(nb.max(nb.sub(1.0 + g2, nb.mul(mu, 2.0 * g)), 1e-4), 1.5)
    return nb.div(1.0 - g2, denom)


def build_cloud_slice(version):
    """Cloud density at one height along the view ray, plus light reaching it."""
    ng, nb, gin, gout = new_group("OS Cloud Slice", [
        ("View", "vector", (0, 0, 1)),
        ("Light Dir", "vector", (0, 0, 1)),
        ("Height", "float", 1.5, 0, 100),
        ("Frac", "float", 0.5, 0, 1),
        ("Coverage", "float", 0.5, 0, 1),
        ("Density", "float", 1.0, 0, 50),
        ("Scale", "float", 1.0, 0.01, 20),
        ("Puffiness", "float", 0.6, 0, 2),
        ("Thickness", "float", 1.2, 0, 20),
        ("Offset", "vector", (0, 0, 0)),
        ("Evolve", "float", 0.0, -1e6, 1e6),
    ], [("Sigma", "float"), ("Light", "float")], version)
    g = gin.outputs
    vx, vy, vz = nb.sep(g["View"])
    t = nb.div(g["Height"], nb.max(vz, 0.02))
    pos = nb.vadd(nb.comb(nb.mul(vx, t), nb.mul(vy, t), g["Height"]), g["Offset"])
    frac = g["Frac"]

    # Cumulus profile: flat base, tops that narrow with height.
    # Noise values centre on 0.5, so this maps coverage 0.35 to scattered
    # cumulus, 0.55 to about half the sky and 1 to a closed deck.
    thr = nb.add(nb.sub(0.72, nb.mul(g["Coverage"], 0.42)), nb.mul(nb.mul(frac, frac), 0.28))
    base_fade = nb.smooth(frac, 0.0, 0.12)

    def density(p, detail):
        q = nb.vscale(p, nb.mul(g["Scale"], 0.45))
        n = nb.nfac(q, 1.0, detail, 0.55, dims="4D", w=nb.mul(g["Evolve"], 0.05))
        return q, n

    q, shape = density(pos, 5.0)
    erode = nb.nfac(q, 4.0, 2.0, 0.5)
    edge = nb.mul(nb.mul(nb.sub(erode, 0.5), g["Puffiness"]), 0.15)
    dens = nb.clamp01(nb.mul(nb.sub(nb.sub(shape, thr), edge), 5.0))
    sigma = nb.mul(nb.mul(dens, base_fade), g["Density"])

    # Light: how much cloud lies between this point and the sun or moon.
    lpos = nb.vadd(pos, nb.vscale(g["Light Dir"], nb.mul(g["Thickness"], 0.35)))
    _, lshape = density(lpos, 2.0)
    ldens = nb.clamp01(nb.mul(nb.sub(lshape, thr), 5.0))
    light = nb.exp(nb.mul(nb.mul(ldens, g["Density"]), -2.5))
    light = nb.lerp(light, 1.0, nb.mul(nb.mul(frac, frac), 0.4))
    # Deep inside a thick, closed deck little sunlight survives: the base of
    # an overcast sky is grey, not sunlit.
    depth = nb.mul(nb.mul(nb.one_minus(frac), g["Thickness"]),
                   nb.mul(nb.mul(g["Coverage"], g["Coverage"]), g["Density"]))
    light = nb.mul(light, nb.exp(nb.mul(depth, -1.2)))

    nb.link(sigma, gout.inputs["Sigma"])
    nb.link(light, gout.inputs["Light"])
    return ng


def build_clouds(slice_group, version):
    ng, nb, gin, gout = new_group("OS Clouds", [
        ("View", "vector", (0, 0, 1)),
        ("Light Dir", "vector", (0, 0, 1)),
        ("Light Color", "color", (1, 1, 1)),
        ("Ambient", "color", (0.3, 0.4, 0.5)),
        ("Flash", "color", (0, 0, 0)),
        ("Coverage", "float", 0.5, 0, 1),
        ("Density", "float", 1.0, 0, 50),
        ("Height", "float", 1.5, 0.05, 50),
        ("Thickness", "float", 1.2, 0, 20),
        ("Scale", "float", 1.0, 0.01, 20),
        ("Puffiness", "float", 0.6, 0, 2),
        ("Darkness", "float", 0.0, 0, 1),
        ("Color", "color", (1, 1, 1)),
        ("Offset", "vector", (0, 0, 0)),
        ("Evolve", "float", 0.0, -1e6, 1e6),
    ], [("Color", "color"), ("Alpha", "float"), ("Distance", "float")], version)
    g = gin.outputs
    view = g["View"]
    _, _, vz = nb.sep(view)
    up = nb.smooth(vz, 0.0, 0.025)

    mu = nb.dot(view, g["Light Dir"])
    phase = nb.add(nb.mul(_hg(nb, mu, 0.7), 0.45), nb.mul(_hg(nb, mu, -0.15), 0.55))
    phase = nb.min(phase, 6.0)
    dark = g["Darkness"]
    direct = nb.vscale(nb.vmul(g["Light Color"], g["Color"]),
                       nb.mul(phase, nb.sub(1.0, nb.mul(dark, 0.75))))
    ambient = nb.vscale(nb.vmul(g["Ambient"], g["Color"]), nb.sub(1.0, nb.mul(dark, 0.7)))

    # Path length through one slice; grazing rays cross more cloud.
    step = nb.div(nb.div(g["Thickness"], float(CLOUD_SLICES)), nb.max(vz, 0.08))
    jitter = nb.white(nb.vscale(view, 5331.0))

    colour, trans = None, None
    for i in range(CLOUD_SLICES):
        frac = nb.div(nb.add(jitter, float(i)), float(CLOUD_SLICES))
        s = group_node(nb, slice_group)
        nb.set(s, "View", view)
        nb.set(s, "Light Dir", g["Light Dir"])
        nb.set(s, "Height", nb.add(g["Height"], nb.mul(g["Thickness"], frac)))
        nb.set(s, "Frac", frac)
        for key in ("Coverage", "Density", "Scale", "Puffiness", "Thickness", "Offset", "Evolve"):
            nb.set(s, key, g[key])
        sigma = find_output(s, "Sigma")
        alpha = nb.one_minus(nb.exp(nb.mul(nb.mul(sigma, step), -1.6)))
        powder = nb.sub(1.0, nb.mul(nb.exp(nb.mul(sigma, -2.0)), 0.5))
        lit = nb.vscale(direct, nb.mul(find_output(s, "Light"), powder))
        # Tops see more of the sky than the shaded bases.
        amb = nb.vscale(ambient, nb.add(0.45, nb.mul(frac, 0.55)))
        radiance = nb.vadd(nb.vadd(lit, amb), g["Flash"])
        part = nb.vscale(radiance, alpha)
        if colour is None:
            colour, trans = part, nb.one_minus(alpha)
        else:
            colour = nb.vadd(colour, nb.vscale(part, trans))
            trans = nb.mul(trans, nb.one_minus(alpha))

    nb.link(nb.vscale(colour, up), gout.inputs["Color"])
    nb.link(nb.mul(nb.one_minus(trans), up), gout.inputs["Alpha"])
    nb.link(nb.div(g["Height"], nb.max(vz, 0.02)), gout.inputs["Distance"])
    return ng


def build_cirrus(version):
    """Thin, streaky ice clouds on a single high sheet."""
    ng, nb, gin, gout = new_group("OS Cirrus", [
        ("View", "vector", (0, 0, 1)),
        ("Light Dir", "vector", (0, 0, 1)),
        ("Light Color", "color", (1, 1, 1)),
        ("Ambient", "color", (0.3, 0.4, 0.5)),
        ("Coverage", "float", 0.0, 0, 1),
        ("Height", "float", 8.0, 0.1, 50),
        ("Scale", "float", 1.0, 0.01, 20),
        ("Direction", "float", 0.0, -360, 360, "ANGLE"),
        ("Offset", "vector", (0, 0, 0)),
    ], [("Color", "color"), ("Alpha", "float")], version)
    g = gin.outputs
    view = g["View"]
    vx, vy, vz = nb.sep(view)
    t = nb.div(g["Height"], nb.max(vz, 0.02))
    p = nb.vadd(nb.comb(nb.mul(vx, t), nb.mul(vy, t), 0.0), g["Offset"])
    p = nb.rotate(p, "Z", g["Direction"])
    px, py, _ = nb.sep(p)
    sc = g["Scale"]
    streak = nb.comb(nb.mul(nb.mul(px, sc), 0.12), nb.mul(nb.mul(py, sc), 0.45), 0.0)
    n = nb.nfac(streak, 1.0, 5.0, 0.58, 0.6)
    lo = nb.sub(1.0, nb.mul(g["Coverage"], 0.55))
    dens = nb.smooth(n, lo, nb.add(lo, 0.22))
    patch = nb.nfac(nb.comb(nb.mul(nb.mul(px, sc), 0.03), nb.mul(nb.mul(py, sc), 0.03), 3.0), 1.0, 2.0)
    dens = nb.mul(dens, nb.smooth(patch, nb.sub(0.75, g["Coverage"]), nb.sub(0.95, g["Coverage"])))
    up = nb.smooth(vz, 0.02, 0.25)
    alpha = nb.mul(nb.mul(dens, 0.6), up)
    mu = nb.dot(view, g["Light Dir"])
    phase = nb.min(nb.add(nb.mul(_hg(nb, mu, 0.8), 0.5), 0.5), 8.0)
    colour = nb.vadd(nb.vscale(g["Light Color"], nb.mul(phase, 0.9)), g["Ambient"])
    nb.link(nb.vscale(colour, alpha), gout.inputs["Color"])
    nb.link(alpha, gout.inputs["Alpha"])
    return ng


RAINBOW = [  # (position across the bow, colour); inside -> outside of the primary
    (0.00, (0.0, 0.0, 0.0)),
    (0.12, (0.35, 0.0, 0.6)),
    (0.28, (0.0, 0.15, 1.0)),
    (0.45, (0.0, 0.9, 0.2)),
    (0.60, (1.0, 0.9, 0.0)),
    (0.75, (1.0, 0.35, 0.0)),
    (0.88, (0.9, 0.0, 0.0)),
    (1.00, (0.0, 0.0, 0.0)),
]


def build_fx(version):
    """Rainbow, 22 degree ice halo and lightning."""
    ng, nb, gin, gout = new_group("OS Sky FX", [
        ("View", "vector", (0, 0, 1)),
        ("Sun", "vector", (0, 0, 1)),
        ("Sun Light", "color", (1, 1, 1)),
        ("Rainbow", "float", 0.0, 0, 10),
        ("Halo", "float", 0.0, 0, 10),
        ("Lightning", "float", 0.0, 0, 10),
        ("Cloud Height", "float", 1.5, 0.05, 50),
        ("Time", "float", 0.0, -1e6, 1e6),
    ], [("Rainbow", "color"), ("Halo", "color"), ("Bolt", "color"), ("Flash", "color")], version)
    g = gin.outputs
    view, sun = g["View"], g["Sun"]
    vx, vy, vz = nb.sep(view)
    _, _, sz = nb.sep(sun)
    up = nb.smooth(vz, -0.002, 0.01)
    deg = 180.0 / math.pi

    # Rainbow: primary bow 40.6-42.4 degrees from the antisolar point,
    # secondary bow 50-53.5 degrees with the colours reversed.
    anti = nb.mul(nb.math("ARCCOSINE", nb.mul(nb.dot(view, sun), -1.0)), deg)
    primary = nb.ramp(nb.remap(anti, 39.8, 43.2), RAINBOW)
    secondary = nb.ramp(nb.remap(anti, 54.0, 49.6), RAINBOW)
    inside = nb.mul(nb.smooth(anti, 41.0, 38.0), 0.06)  # brighter sky inside the bow
    bow = nb.vadd(nb.vadd(primary, nb.vscale(secondary, 0.35)), nb.comb(inside, inside, inside))
    sun_up = nb.smooth(sz, -0.01, 0.05)
    strength = nb.mul(nb.mul(g["Rainbow"], sun_up), nb.mul(up, 0.05))
    nb.link(nb.vscale(nb.vmul(bow, g["Sun Light"]), strength), gout.inputs["Rainbow"])

    # 22 degree halo: red inner edge, fading outwards; faint 46 degree halo.
    from_sun = nb.mul(nb.math("ARCCOSINE", nb.dot(view, sun)), deg)
    ring = nb.ramp(nb.remap(from_sun, 21.4, 25.5), [
        (0.0, (0.0, 0.0, 0.0)), (0.08, (1.0, 0.35, 0.15)), (0.2, (1.0, 0.85, 0.6)),
        (0.4, (0.75, 0.8, 0.9)), (1.0, (0.0, 0.0, 0.0))])
    big = nb.mul(nb.exp(nb.mul(nb.mul(nb.sub(from_sun, 46.0), nb.sub(from_sun, 46.0)), -0.5)), 0.25)
    halo = nb.vadd(ring, nb.comb(big, big, big))
    strength = nb.mul(nb.mul(g["Halo"], up), 0.02)
    nb.link(nb.vscale(nb.vmul(halo, g["Sun Light"]), strength), gout.inputs["Halo"])

    # Lightning: the time is cut into half-second slots; each slot may hold a
    # strike at a random bearing and distance, with a flickering decay.
    time2 = nb.mul(g["Time"], 2.0)
    slot = nb.math("FLOOR", time2)
    phase = nb.math("FRACT", time2)
    strike = nb.math("LESS_THAN", nb.white(None, "1D", slot), nb.mul(g["Lightning"], 0.35))
    # A strike lasts a few frames and flickers as the channel re-strikes.
    pulse = nb.math("COSINE", nb.mul(phase, 40.0))
    flicker = nb.mul(nb.exp(nb.mul(phase, -7.0)), nb.add(0.5, nb.mul(nb.mul(pulse, pulse), 0.5)))
    env = nb.mul(nb.mul(flicker, strike), nb.min(g["Lightning"], 1.0))

    bearing = nb.mul(nb.sub(nb.white(None, "1D", nb.add(slot, 3.17)), 0.5), 2.0 * math.pi)
    dist = nb.add(nb.mul(nb.white(None, "1D", nb.add(slot, 7.71)), 10.0), 3.0)
    top = nb.math("ARCTANGENT", nb.div(g["Cloud Height"], dist))
    az = nb.math("ARCTAN2", vx, vy)
    el = nb.math("ARCSINE", vz)
    d_az = nb.math("WRAP", nb.sub(az, bearing), math.pi, -math.pi)
    wiggle = nb.mul(nb.sub(nb.nfac(None, 1.0, 3.0, 0.6, dims="1D",
                                   w=nb.add(nb.div(el, nb.max(top, 0.01)), nb.mul(slot, 1.3))),
                           0.5), nb.mul(top, 0.6))
    fine = nb.mul(nb.sub(nb.nfac(None, 1.0, 2.0, dims="1D", w=nb.add(nb.mul(el, 150.0), slot)), 0.5),
                  0.008)
    coarse = nb.sub(nb.mul(d_az, nb.cos(el)), wiggle)
    off = nb.abs(nb.sub(coarse, fine))
    core = nb.exp(nb.mul(nb.mul(nb.div(off, 0.0012), nb.div(off, 0.0012)), -1.0))
    glow = nb.mul(nb.exp(nb.div(nb.abs(coarse), -0.02)), 0.06)
    span = nb.mul(nb.smooth(el, -0.005, 0.002), nb.smooth(el, top, nb.mul(top, 0.85)))
    bolt = nb.mul(nb.mul(nb.add(core, glow), span), nb.mul(env, 40.0))
    tint = (0.78, 0.82, 1.0)
    nb.link(nb.vscale(tint, bolt), gout.inputs["Bolt"])
    # The flash lights the clouds, strongest around the strike.
    near = nb.add(0.08, nb.exp(nb.mul(nb.abs(d_az), -3.0)))
    nb.link(nb.vscale(tint, nb.mul(nb.mul(env, near), 0.5)), gout.inputs["Flash"])
    return ng
