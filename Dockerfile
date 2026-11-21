# Built by the scorer on linux/amd64. Match sandbox: no network, read-only root (writable /tmp),
# 1 CPU, 512 MB, uid 65534, map mounted at /arena. Base images pinned because finalists are rebuilt.
FROM oven/bun:1.4.4-slim AS bun
FROM python:3.13.9-slim
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /bot
COPY mechfight.py bot.py hybrid.py ./
COPY ttun/ ./ttun/
ENV MR_TTUN=11350d3
ENV MR_TTUN_SALT=4
ENTRYPOINT ["python3", "-u", "/bot/hybrid.py"]
