"""Live DRC (and later LVS) for KLayout, roadmap Phase 5.

The checking core (clip, tier 0, the PDK deck, results, dirty areas) runs
without the GUI; ``ui`` adds the menu entries, the live mode and the
marker browser. Tiers:

  0  in-process width/space checks on the clipped area (instant)
  1  the PDK's KLayout deck on a clipped GDS, in a background process
"""

__version__ = "0.1.0"
