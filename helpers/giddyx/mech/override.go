package mech

// Free-for-all parameter overrides (oval-pilot addition, MIT like the rest of this package).
// GPFFA="Vulture=0.4,Odds=0.7,Ghost=false" sets Params fields by name once a free-for-all is confirmed.

import (
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
