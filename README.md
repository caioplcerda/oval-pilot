# oval-pilot

A `mechfight/1` bot.

Based on [LanceHuang245/mech-royale](https://github.com/LanceHuang245/mech-royale) at commit `6bdf03b` (MIT). The original copyright is kept in `LICENSE`. Our changes are listed in the git history.

## Hybrid controller (hybrid.py)

Practice play comes from TTUN/r1ver's MIT-licensed bot ([varchaskukreja/TTUN](https://github.com/varchaskukreja/TTUN), files vendored unchanged under `ttun/<commit>/`, license in `ttun/LICENSE`), run with Bun. As soon as our bot detects a free-for-all, our own controller (`bot.py`) takes over for the rest of the match.

The default practice helper is now the Team Kanyaraasi Go bot (MIT, adapted from giddygiddyboy's MIT bot), vendored unchanged from [devakchow/team-kanyaraasi-mech-royale](https://github.com/devakchow/team-kanyaraasi-mech-royale) at `fdf06a3` under `helpers/kanya/`, with both license notices (`helpers/kanya/LICENSE`, `helpers/kanya/THIRD_PARTY_LICENSES`). It is compiled in the Docker build.

`MR_NOSWITCH=1` makes the helper play the whole match (our bot keeps running only as a fallback if the helper crashes or stalls). The giddygiddyboy Go bot (MIT, [justnau/giddygiddyboy-mech-royale](https://github.com/justnau/giddygiddyboy-mech-royale) at `70c8b23`, license in `helpers/giddy70c8b23/LICENSE`) is vendored unchanged under `helpers/giddy70c8b23/`.

## Final entry (current)

The final entry is the giddygiddyboy Go bot (MIT, [justnau/giddygiddyboy-mech-royale](https://github.com/justnau/giddygiddyboy-mech-royale)) at `898692e`, vendored unchanged under `helpers/giddy898692e/` (license in `helpers/giddy898692e/LICENSE`). It plays the whole match (`MR_NOSWITCH=1`). Our Python bot (`bot.py`, based on LanceHuang245's MIT bot) runs alongside as a fallback if the helper crashes or stalls. `MR_TTUN_SALT` only changes the random seed the helper is given. `helpers/giddyx/` is our experimental fork with free-for-all-only parameter overrides (not used in the final entry).
