package main

import (
	"bufio"
	"errors"
	"os"
	"path"
	"strconv"
	"strings"
	"time"
)

type policy struct {
	patterns []string
	maxFile  int64
}
type cachedHash struct {
	Size     int64
	Modified int64
	SHA      string
	Verified int64
}

var cacheLoaded bool
var hashCache = map[string]cachedHash{}

func loadPolicy(root string) (policy, error) {
	p := policy{maxFile: 1024 * 1024 * 1024}
	raw := os.Getenv("PI_WORKSPACE_EXCLUDE")
	if f, e := os.Open(root + string(os.PathSeparator) + ".projectexpert-workspaceignore"); e == nil {
		defer f.Close()
		s := bufio.NewScanner(f)
		for s.Scan() {
			raw += "\n" + s.Text()
		}
		if e = s.Err(); e != nil {
			return p, e
		}
	} else if !os.IsNotExist(e) {
		return p, e
	}
	if v := os.Getenv("PI_WORKSPACE_MAX_FILE_BYTES"); v != "" {
		n, e := strconv.ParseInt(v, 10, 64)
		if e != nil || n < 1 {
			return p, errors.New("invalid PI_WORKSPACE_MAX_FILE_BYTES")
		}
		p.maxFile = n
	}
	for _, line := range strings.FieldsFunc(raw, func(c rune) bool { return c == '\n' || c == ',' }) {
		s := strings.TrimSpace(line)
		if s == "" || strings.HasPrefix(s, "#") {
			continue
		}
		if strings.HasPrefix(s, "!") || strings.Contains(s, "**") || strings.Contains(s, "\\") || strings.Contains(s, "..") || strings.Contains(s, ":") {
			return p, errors.New("unsupported workspace exclusion pattern")
		}
		s = strings.TrimPrefix(s, "/")
		if _, e := path.Match(strings.TrimSuffix(s, "/"), "probe"); e != nil {
			return p, e
		}
		p.patterns = append(p.patterns, s)
	}
	return p, nil
}
func (p policy) excludes(name string, dir bool) bool {
	for _, pattern := range p.patterns {
		folder := strings.HasSuffix(pattern, "/")
		pat := strings.TrimSuffix(pattern, "/")
		if folder {
			if strings.Contains(pat, "/") {
				if (dir && name == pat) || strings.HasPrefix(name, pat+"/") {
					return true
				}
			} else {
				parts := strings.Split(name, "/")
				for i, part := range parts {
					if ok, _ := path.Match(pat, part); ok && (dir || i < len(parts)-1) {
						return true
					}
				}
			}
			continue
		}
		if !strings.Contains(pat, "/") {
			for _, part := range strings.Split(name, "/") {
				if ok, _ := path.Match(pat, part); ok {
					return true
				}
			}
		} else if ok, _ := path.Match(pat, name); ok {
			return true
		}
	}
	return false
}
func cached(path string, size, mod int64) (string, bool) {
	v, ok := hashCache[path]
	return v.SHA, ok && v.Size == size && v.Modified == mod && time.Now().Unix()-v.Verified < int64(verifyInterval().Seconds())
}

func debounceInterval() time.Duration {
	if raw := os.Getenv("PI_WORKSPACE_DEBOUNCE_MS"); raw != "" {
		if n, e := strconv.Atoi(raw); e == nil && n >= 100 && n <= 60000 {
			return time.Duration(n) * time.Millisecond
		}
	}
	return 1500 * time.Millisecond
}
func verifyInterval() time.Duration {
	if raw := os.Getenv("PI_WORKSPACE_VERIFY_INTERVAL_SECONDS"); raw != "" {
		if n, e := strconv.Atoi(raw); e == nil && n >= 5 && n <= 86400 {
			return time.Duration(n) * time.Second
		}
	}
	return 300 * time.Second
}
