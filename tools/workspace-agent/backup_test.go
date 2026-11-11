package main

import (
	"archive/tar"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func testCheckpoint(t *testing.T, files map[string][]byte) string {
	t.Helper()
	root := t.TempDir()
	m := Checkpoint{Schema: 1, Product: "0.1.0", Generation: "gen", Profile: "profile", Files: map[string]File{}}
	for name, data := range files {
		path := filepath.Join(root, filepath.FromSlash(name))
		os.MkdirAll(filepath.Dir(path), 0700)
		os.WriteFile(path, data, 0600)
		h := sha256.Sum256(data)
		m.Files[name] = File{Size: int64(len(data)), SHA: hex.EncodeToString(h[:])}
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(root, "checkpoint-manifest.json"), data, 0600)
	return root
}
func TestBackupRequiresActualGenerationAndNoCredentials(t *testing.T) {
	for _, files := range []map[string][]byte{{}, {"settings.json": []byte(`{"api_key":"secret"}`)}, {".env": []byte("key")}, {"runtime-state/snapshot.json": []byte(`{"active":{"active_index_generation":"other","embedding_profile_identity":"profile"}}`)}} {
		root := testCheckpoint(t, files)
		if _, err := verifyBackup(root); err == nil {
			t.Fatal("accepted unusable/sensitive snapshot")
		}
	}
	root := testCheckpoint(t, map[string][]byte{"runtime-state/snapshot.json": []byte(`{"active":{"active_index_generation":"gen","embedding_profile_identity":"profile"}}`), "embeddings.sqlite": []byte("vector")})
	if _, err := verifyBackup(root); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(root, "extra"), []byte("unlisted"), 0600)
	if _, err := verifyBackup(root); err == nil {
		t.Fatal("accepted unlisted")
	}
}
func TestBackupArchiveRejectsTraversalAndLinks(t *testing.T) {
	for _, name := range []string{"../outside", "/outside", "a/../b", "a\\b"} {
		var stream bytes.Buffer
		tw := tar.NewWriter(&stream)
		tw.WriteHeader(&tar.Header{Name: name, Mode: 0600, Size: 1})
		tw.Write([]byte("x"))
		tw.Close()
		if err := extractBackup(&stream, t.TempDir()); err == nil {
			t.Fatal("accepted", name)
		}
	}
}
func TestSourceOpenRejectsSymlinkParents(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	os.WriteFile(filepath.Join(outside, "private"), []byte("secret"), 0600)
	if err := os.Symlink(outside, filepath.Join(root, "linked")); err != nil {
		t.Skip(err)
	}
	if f, err := openSource(filepath.Join(root, "linked", "private")); err == nil {
		f.Close()
		t.Fatal("followed parent link")
	}
}

func TestWindowsCRLFImageConfiguration(t *testing.T) {
	t.Setenv("PI_IMAGE", "")
	kit := t.TempDir()
	os.WriteFile(filepath.Join(kit, "deployment.env"), []byte("# comment\r\nPI_IMAGE=\"projectexpert:fixture\"\r\n"), 0600)
	if image := configuredImage(kit); image != "projectexpert:fixture" {
		t.Fatal(image)
	}
	t.Setenv("PI_IMAGE", "override:exact")
	if configuredImage(kit) != "override:exact" {
		t.Fatal("environment precedence")
	}
}
