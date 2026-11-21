#!/usr/bin/env bash
# A/B harness. Usage:
#   tools/ab.sh league <matches> '<labelA=SPEC=N>' '<labelB=SPEC=N>' [more entries...]   (FFA, econ on)
#   tools/ab.sh practice <matches> '<MR_FLAGS>' [botfile]                                (1 vs 15 house sim)
# Splits work over $WORKERS processes (default 11) and merges results.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-$(uv python find 3.13)}
WORKERS=${WORKERS:-11}
mode=$1; n=$2; shift 2
out=$(mktemp -d)
per=$(( (n + WORKERS - 1) / WORKERS ))
if [[ $mode == league ]]; then
  args=(); for e in "$@"; do args+=(--entry "$e"); done
  for ((w=0; w<WORKERS; w++)); do
    "$PY" tools/league.py --kit . --econ --matches $per --start $((w*per + ${SEED0:-0})) "${args[@]}" > "$out/$w.txt" 2>/dev/null &
  done; wait
  "$PY" tools/league_merge.py "$out"/*.txt
else
  flags=$1; botfile=${2:-}
  for ((w=0; w<WORKERS; w++)); do
    MR_FLAGS="$flags" "$PY" tools/sim.py --kit . --matches $per --start $((w*per + ${SEED0:-0})) ${botfile:+--botfile "$botfile"} > "$out/$w.txt" 2>/dev/null &
  done; wait
  cat "$out"/*.txt | "$PY" -c "
import sys,json,math
v=[json.loads(l)['points'] for l in sys.stdin if l.startswith('{\"place')]
m=sum(v)/len(v); sd=math.sqrt(sum((x-m)**2 for x in v)/max(1,len(v)-1))
print('practice flags=$flags n=%d mean %.2f se %.2f'%(len(v),m,sd/math.sqrt(len(v))))"
fi
rm -rf "$out"
