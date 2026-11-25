"""Check an area synchronously (batch, tests); the GUI uses the same
steps with the deck in a background process."""

import os
import subprocess
import tempfile

from . import clip as clip_mod
from . import deck as deck_mod
from . import pdk as pdk_mod
from . import results, tier0


def prepare(layout, cell, window, pdk=None, workdir=None):
    """Clip and write the GDS for tier 1. Returns a dict for finish()."""
    pdk = pdk or pdk_mod.current()
    halo = pdk_mod.HALO.get(pdk, 2.0)
    lay, top, cbox = clip_mod.clip(layout, cell, window, halo)
    work = workdir or tempfile.mkdtemp(prefix="live_drc_")
    gds = os.path.join(work, "clip.gds")
    lay.write(gds)
    report = os.path.join(work, "clip.lyrdb")
    t0 = tier0.check(lay, top, pdk)
    return {"pdk": pdk, "window": window, "cbox": cbox, "band": halo / 2.0, "gds": gds, "report": report,
            "top": top.name, "work": work, "t0": t0,
            "cmd": deck_mod.command(gds, top.name, report, pdk)}


def finish(job):
    """{tier: kept markers} once the deck (if any) has written its report."""
    out = {0: results.keep(job["t0"], job["window"], job["cbox"], job["band"])}
    if job["cmd"] and os.path.isfile(job["report"]):
        out[1] = results.keep(deck_mod.read_report(job["report"]), job["window"], job["cbox"], job["band"])
    return out


def check_area(layout, cell, window, pdk=None, tiers=(0, 1), timeout=600):
    """Run the tiers on ``window`` (DBox, um) of ``cell`` and return
    {tier: [(rule, shape)]}."""
    job = prepare(layout, cell, window, pdk)
    if 1 in tiers and job["cmd"]:
        subprocess.run(job["cmd"], capture_output=True, text=True, timeout=timeout, cwd=job["work"])
    res = finish(job)
    return {t: m for t, m in res.items() if t in tiers}
