# Built by the scorer on linux/amd64. Match sandbox: no network, read-only root (writable /tmp),
# 1 CPU, 512 MB, uid 65534, map mounted at /arena. Base images pinned because finalists are rebuilt.
FROM golang:1.26.1-bookworm@sha256:ab3d6955bbc813a0f3fdf220c1d817dd89c0b3f283777db8ece4a32fe7858edd AS gobuild
WORKDIR /src
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOTELEMETRY=off
COPY helpers/giddyy/go.mod ./
COPY helpers/giddyy/mech ./mech
COPY helpers/giddyy/cmd/bot ./cmd/bot
RUN go build -mod=readonly -trimpath -buildvcs=false -ldflags="-s -w -buildid=" -o /mechbot ./cmd/bot

FROM oven/bun:1.4.4-slim AS bun
FROM python:3.13.9-slim
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
COPY --from=gobuild /mechbot /usr/local/bin/mechbot
WORKDIR /bot
COPY mechfight.py bot.py hybrid.py ./
COPY ttun/ ./ttun/
COPY helpers/giddyy/LICENSE ./helpers/giddyy/
ENV MR_TTUN=11350d3 MR_HELPER=/usr/local/bin/mechbot MR_NOSWITCH=1 GPFFA=FightBoost=30,DodgeBoost=15,ThreatBoost=20,SpeedUp=true MR_FP_GROUPS=4 MR_FP_ALT_GROUPS=0
ENTRYPOINT ["python3", "-u", "/bot/hybrid.py"]
