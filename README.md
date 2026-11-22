# Antalos: Mech Royale bot

Original `mechfight/1` bot by team Antalos for the Builders Buildathon (Mech Royale track).

- `bot.py`: decision logic: arming (laser + lightning first), gun lead and laser/lightning firing, facing threats, retreating to cover, zone timing, free-for-all detection with selective engagement, boost-strafing, quiet movement, cube/crate/drone economy, upgrade choice.
- `world.py`: our map model: terrain, rasterised solid prisms, line of sight, walk grid and time-sliced A*.
- `mechfight.py`: the official starter-kit protocol wrapper (unchanged).

Standard library only. Build: `docker build --platform linux/amd64 -t antalos .`
