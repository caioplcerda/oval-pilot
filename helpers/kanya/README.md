# Team Kanyaraasi — Mech Royale

This package adapts [justnau/giddygiddyboy-mech-royale](https://github.com/justnau/giddygiddyboy-mech-royale)
at pinned commit `345c0de2f43f5f27a4ecf74c1c25c789d00fbc49`, licensed MIT, copyright 2026 giddygiddyboy.
The complete upstream notice is in `THIRD_PARTY_LICENSES`; Team Kanyaraasi's
packaging license is `LICENSE`. Both complete notices are included in the image.

Three `mech/*.go` files and `go.mod` are unchanged. `cmd/bot/main.go`
retains the previously validated map-construction and recovered-panic stderr
diagnostics. `mech/brain.go` changes only one default parameter assignment:
it enables the existing `Lethal` Laser-release heuristic. The flag is inherited
by the existing Opening and squad profiles. All targeting, movement, geometry,
other parameters, and the original release predicate remain unchanged.
The flat-map fallback and recovered/coasting actions remain; strict validation
rejects either fallback or recovered panic.

The compiler is the upstream pinned Go 1.26.1 image; the final runtime is scratch,
uid 65534, with no third-party modules or runtime dependencies. Toolchain/module
fetching and telemetry are disabled during compilation. Build for linux/amd64;
run under the organizer's sandbox with its read-only arena at `/arena` and
64 MB writable `/tmp`. HOME and TMPDIR point to `/tmp`.
This adapts our selected P036 control, public commit `d9c557f8983f2b8658403343686921d57f1de788`,
which measured 5.60 in one official practice aggregate. That measurement belongs
to the control, not this unscored adaptation. The isolated flag was inspired by
the same author's later MIT revision `64724a2ad873f9a740295d1984fcf2dc4cab5d4b`;
its 14 m pursuit and other defaults are excluded. The existing heuristic may
release an aligned partly charged Laser when its damage estimate exceeds the
target's HP with a 20% reserve. Unknown armor, occlusion and action ordering mean
that estimate is not a guaranteed kill. No placement gain is claimed.

Runtime source SHA-256 values:
- `cmd/bot/main.go`: `a4259e0c2f9cf8de66a04844fc7a4d0ca4bc2070b987905c14723895939b7f93`
- `go.mod`: `51496525f2844bdd830c5d1e202b54bd97d9dfad96381782fea13fa51e6fc3fb`
- `mech/brain.go`: `4d55806a90df27969dae5cafdfa0a098e0a6bdac0a9aa07313918161c9688a30`
- `mech/export.go`: `3f0384222b15eddf9f516b74e89beefe44e65a10fef294735424f042d982967b`
- `mech/types.go`: `ab43e63ca989678290d180a5cdb54f0de04d73bf136a7558ad40fc039e76ed71`
- `mech/world.go`: `a2cf879007fc3bc49cfc0bb90e6e99e8cff5a9413f85499c6b165bfee6d27ec4`
