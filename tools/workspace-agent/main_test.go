package main

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestScanIncremental(t *testing.T) {
	root := t.TempDir()
	os.WriteFile(filepath.Join(root, "a"), []byte("one"), 0600)
	os.WriteFile(filepath.Join(root, ".env"), []byte("secret"), 0600)
	os.Mkdir(filepath.Join(root, "project-knowledge"), 0700)
	os.WriteFile(filepath.Join(root, "project-knowledge", "wiki"), []byte("canonical"), 0600)
	a, e := scan(root)
	if e != nil {
		t.Fatal(e)
	}
	b, e := scan(root)
	if e != nil || a.Generation != b.Generation || len(a.Files) != 1 {
		t.Fatal("unstable or exclusions failed")
	}
	os.WriteFile(filepath.Join(root, "a"), []byte("two"), 0600)
	b, e = scan(root)
	if e != nil || a.Files["a"] == b.Files["a"] {
		t.Fatal("same-size edit missed")
	}
}
func TestThirtyThousand(t *testing.T) {
	if testing.Short() {
		t.Skip("large native scan")
	}
	root := t.TempDir()
	for i := 0; i < 30000; i++ {
		if e := os.WriteFile(filepath.Join(root, fmt.Sprint(i)), []byte("source"), 0600); e != nil {
			t.Fatal(e)
		}
	}
	a, e := scan(root)
	if e != nil {
		t.Fatal(e)
	}
	b, e := scan(root)
	if e != nil || len(a.Files) != 30000 || a.Generation != b.Generation {
		t.Fatal("large reconcile differs")
	}
	var changed int
	for n, f := range b.Files {
		if a.Files[n] != f {
			changed++
		}
	}
	if changed != 0 {
		t.Fatal("unchanged bytes would transfer")
	}
}

func TestPolicy(t *testing.T) {
	root := t.TempDir()
	t.Setenv("PI_WORKSPACE_EXCLUDE", "folder/,*.tar,*.sql.gz,exact name,資料/")
	p, e := loadPolicy(root)
	if e != nil {
		t.Fatal(e)
	}
	for _, name := range []string{"folder/sub/a", "nested/archive.tar", "dump.sql.gz", "exact name", "資料/a"} {
		if !p.excludes(name, false) {
			t.Errorf("not excluded: %s", name)
		}
	}
	if p.excludes("source.go", false) {
		t.Fatal("excluded source")
	}
	for _, pattern := range []string{"!keep", "**/bad", "../bad", "a["} {
		t.Setenv("PI_WORKSPACE_EXCLUDE", pattern)
		if _, e := loadPolicy(root); e == nil {
			t.Errorf("accepted unsupported %s", pattern)
		}
	}
}
func TestExclusionsChangeManifest(t *testing.T) {
	root := t.TempDir()
	os.Mkdir(filepath.Join(root, "nested"), 0700)
	os.WriteFile(filepath.Join(root, "nested", "dump.sql.gz"), []byte("dump"), 0600)
	a, e := scan(root)
	if e != nil || len(a.Files) != 1 {
		t.Fatal(e)
	}
	os.WriteFile(filepath.Join(root, ".projectexpert-workspaceignore"), []byte("*.sql.gz\n"), 0600)
	b, e := scan(root)
	if e != nil {
		t.Fatal(e)
	}
	if _, ok := b.Files["nested/dump.sql.gz"]; ok {
		t.Fatal("excluded file retained")
	}
	t.Setenv("PI_WORKSPACE_MAX_FILE_BYTES", "1")
	b, e = scan(root)
	if e != nil || len(b.Files) != 0 {
		t.Fatal("oversize files were hashed")
	}
}
func TestForcedHashVerification(t *testing.T) {
	root := t.TempDir()
	p := filepath.Join(root, "a")
	os.WriteFile(p, []byte("one"), 0600)
	a, e := scan(root)
	if e != nil {
		t.Fatal(e)
	}
	info, _ := os.Stat(p)
	os.WriteFile(p, []byte("two"), 0600)
	os.Chtimes(p, info.ModTime(), info.ModTime())
	v := hashCache[p]
	v.Verified = 0
	hashCache[p] = v
	b, e := scan(root)
	if e != nil || a.Files["a"] == b.Files["a"] {
		t.Fatal("periodic hash missed same stat edit")
	}
}

func TestFolderExclusionDoesNotOmitSameNamedFile(t *testing.T) {
	p := policy{patterns: []string{"dumps/"}}
	if p.excludes("dumps", false) {
		t.Fatal("folder rule omitted ordinary file")
	}
	if !p.excludes("dumps", true) || !p.excludes("nested/dumps/archive", false) {
		t.Fatal("folder rule did not omit directory")
	}
}

func TestVolatileDefaultsPreserveProjectConfiguration(t *testing.T) {
	for _, name := range []string{".idea/workspace.xml", "nested/.idea/workspace.xml", ".worktrees/copy/source.go"} {
		if !excluded(name) {
			t.Errorf("volatile duplicate path included: %s", name)
		}
	}
	for _, name := range []string{".idea/compiler.xml", "src/worktrees/model.go", "src/application.go"} {
		if excluded(name) {
			t.Errorf("project configuration excluded: %s", name)
		}
	}
}
func TestChangedSourceDiagnosticIsDeterministic(t *testing.T) {
	before := Manifest{Files: map[string]File{"z.java": {1, "a"}, "a.java": {1, "b"}}}
	after := Manifest{Files: map[string]File{"z.java": {1, "c"}, "a.java": {1, "d"}}}
	if firstChangedSource(before, after) != "a.java" {
		t.Fatal("missing deterministic changed path")
	}
	if firstChangedSource(before, before) != "VCS metadata" {
		t.Fatal("missing VCS diagnostic")
	}
}
