package mech

// Free-for-all parameter overrides (oval-pilot addition, MIT like the rest of this package).
// GPFFA="Vulture=0.4,Odds=0.7,Ghost=false" sets Params fields by name once a free-for-all is confirmed.

import (
	"math"
	"os"
	"reflect"
	"strconv"
	"strings"
)

var ffaOverrides = parseOverrides(os.Getenv("GPFFA"))

type override struct {
	field string
	value string
}

func parseOverrides(s string) []override {
	var out []override
	for _, kv := range strings.Split(s, ",") {
		parts := strings.SplitN(strings.TrimSpace(kv), "=", 2)
		if len(parts) == 2 && parts[0] != "" {
			out = append(out, override{parts[0], parts[1]})
		}
	}
	return out
}

func applyOverrides(p Params, ovs []override) Params {
	v := reflect.ValueOf(&p).Elem()
	for _, o := range ovs {
		f := v.FieldByName(o.field)
		if !f.IsValid() || !f.CanSet() {
			continue
		}
		switch f.Kind() {
		case reflect.Float64:
			if x, err := strconv.ParseFloat(o.value, 64); err == nil {
				f.SetFloat(x)
			}
		case reflect.Bool:
			if x, err := strconv.ParseBool(o.value); err == nil {
				f.SetBool(x)
			}
		}
	}
	return p
}

// Structural free-for-all ideas (oval-pilot): GPX="third,truel".
var ffaX = os.Getenv("GPX")

func xOn(name string) bool { return strings.Contains(","+ffaX+",", ","+name+",") }

// busyWithOther: t is aiming at another tracked mech within 160 m (fighting someone else, not us).
func (b *Brain) busyWithOther(t *Track, now float64, x, y float64) bool {
	toMe := math.Atan2(y-t.Pos[1], x-t.Pos[0])
	if math.Abs(angDiff(t.Aim[0], toMe)) < 0.4 {
		return false
	}
	for _, u := range b.tracks {
		if u.ID == t.ID || now-u.Seen > 2.5 {
			continue
		}
		br := math.Atan2(u.Pos[1]-t.Pos[1], u.Pos[0]-t.Pos[0])
		if math.Abs(angDiff(t.Aim[0], br)) < 0.25 && hyp(u.Pos[0]-t.Pos[0], u.Pos[1]-t.Pos[1]) < 160 {
			return true
		}
	}
	return false
}

// Practice (squad) overrides: GPSQ="FightBoost=40,..." applied on top of squadParams while practice mode is on.
var squadOverrides = parseOverrides(os.Getenv("GPSQ"))

// HomeExpoCost is the original exposure term (kept separate so homeCostX can reuse it).
func (b *Brain) HomeExpoCost(px, py float64) float64 { return b.P.HomeExpo * b.W.Exposure(px, py) }

// homeCostX: minimum-risk home choice with oval-pilot switches (GPX): notclose, farcrowd, edge.
func (b *Brain) homeCostX(o *Obs, px, py, edge float64) float64 {
	rad, w := 80.0, 40.0
	if xOn("farcrowd") {
		rad, w = 130, 80
	}
	crowd := 0.0
	for _, t := range b.tracks {
		if b.now-t.Seen < 20 {
			crowd += math.Max(0, rad-hyp(t.Pos[0]-px, t.Pos[1]-py)) / rad
		}
	}
	for i := range o.Drops {
		crowd += math.Max(0, 60-hyp(o.Drops[i].Pos[0]-px, o.Drops[i].Pos[1]-py)) / 60
	}
	c := b.HomeExpoCost(px, py) + 0.25*hyp(px-o.Self.Pos[0], py-o.Self.Pos[1]) + w*crowd
	if xOn("edge") {
		c -= 10 * edge
	} else {
		c += 10 * edge
	}
	if xOn("notclose") {
		for _, t := range b.tracks {
			if b.now-t.Seen > 20 {
				continue
			}
			dMe := hyp(t.Pos[0]-px, t.Pos[1]-py)
			closest := true
			for _, u := range b.tracks {
				if u.ID != t.ID && b.now-u.Seen < 20 && hyp(t.Pos[0]-u.Pos[0], t.Pos[1]-u.Pos[1]) < dMe {
					closest = false
					break
				}
			}
			if closest && dMe < 220 {
				c += 50
			}
		}
	}
	return c
}
