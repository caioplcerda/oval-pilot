# Antalos Mech Royale bot. Built by the scorer on linux/amd64; runs with no network, read-only root,
# 1 CPU, 512 MB, uid 65534, map mounted at /arena. Base image pinned (finalists are rebuilt).
FROM python:3.13.9-slim
WORKDIR /bot
COPY mechfight.py world.py bot.py ./
ENV AB_PM_FLOOT=0
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
