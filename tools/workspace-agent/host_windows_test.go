package main

import (
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func shortWindowsPath(t *testing.T, path string) string {
	t.Helper()
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		t.Fatal(err)
	}
	buf := make([]uint16, 32768)
	n, err := syscall.GetShortPathName(p, &buf[0], uint32(len(buf)))
	if err != nil || n == 0 || n >= uint32(len(buf)) {
		t.Fatalf("GetShortPathName: length=%d error=%v", n, err)
	}
	return syscall.UTF16ToString(buf[:n])
}

func TestWindowsSourcePathSpellings(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "workspace directory with long name")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "source file with long name.txt")
	if err := os.WriteFile(path, []byte("source contents"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, spelling := range []string{path, `\\?\` + path, shortWindowsPath(t, path)} {
		t.Run(spelling, func(t *testing.T) {
			f, err := openSource(spelling)
			if err != nil {
				t.Fatal(err)
			}
			defer f.Close()
			data, err := io.ReadAll(f)
			if err != nil || string(data) != "source contents" {
				t.Fatalf("read source: %q, %v", data, err)
			}
		})
	}
	if strings.EqualFold(shortWindowsPath(t, path), path) {
		t.Log("8.3 names unavailable on this volume; ordinary and extended paths tested")
	}
}

func TestWindowsSourceRejectsJunctionParent(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	if err := os.WriteFile(filepath.Join(outside, "source.txt"), []byte("outside"), 0600); err != nil {
		t.Fatal(err)
	}
	junction := filepath.Join(root, "redirected directory")
	if out, err := exec.Command("cmd", "/c", "mklink", "/J", junction, outside).CombinedOutput(); err != nil {
		t.Fatalf("create junction: %v: %s", err, out)
	}
	defer os.Remove(junction)
	for _, parent := range []string{junction, shortWindowsPath(t, junction)} {
		f, err := openSource(filepath.Join(parent, "source.txt"))
		if err == nil {
			f.Close()
			t.Fatalf("accepted junction parent %q", parent)
		}
	}
}

func TestWindowsSourceRejectsHardlink(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "source.txt")
	if err := os.WriteFile(path, []byte("source"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Link(path, filepath.Join(dir, "alias.txt")); err != nil {
		t.Fatal(err)
	}
	f, err := openSource(path)
	if err == nil {
		f.Close()
		t.Fatal("accepted multiply linked file")
	}
}

func TestWindowsPathNamespace(t *testing.T) {
	for _, pair := range [][2]string{
		{`\\?\C:\source\file.txt`, `C:\source\file.txt`},
		{`\\?\UNC\server\share\file.txt`, `\\server\share\file.txt`},
		{`C:\source\file.txt`, `C:\source\file.txt`},
	} {
		if got := windowsDOSPath(pair[0]); got != pair[1] {
			t.Errorf("windowsDOSPath(%q) = %q; want %q", pair[0], got, pair[1])
		}
	}
}
