package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func identityHash(text string) string {
	hash := sha256.Sum256([]byte(text))
	return hex.EncodeToString(hash[:])
}
func hostVCS(root string) (map[string]string, error) {
	vcs := map[string]string{"provider": "none", "working_copy_id": identityHash(root)}
	git := func(args ...string) (string, error) {
		raw, e := exec.Command("git", append([]string{"-C", root}, args...)...).Output()
		return strings.TrimSpace(string(raw)), e
	}
	if top, e := git("rev-parse", "--show-toplevel"); e == nil {
		head, err := git("rev-parse", "HEAD")
		if err != nil {
			head = "unborn"
		}
		branch, _ := git("symbolic-ref", "--short", "-q", "HEAD")
		if branch == "" {
			branch = "HEAD"
		}
		common, _ := git("rev-parse", "--git-common-dir")
		if !filepath.IsAbs(common) {
			common = filepath.Join(root, common)
		}
		return map[string]string{"provider": "git", "head": head, "branch": branch, "repository_id": identityHash(filepath.Clean(common)), "working_copy_id": identityHash(root), "source_root_id": identityHash(top)}, nil
	}
	if _, e := os.Stat(filepath.Join(root, ".git")); e == nil {
		return nil, errors.New("Git checkout detected but host Git identity unavailable")
	}
	if _, e := os.Stat(filepath.Join(root, ".svn")); e == nil {
		item := func(name string) (string, error) {
			raw, e := exec.Command("svn", "info", "--show-item", name, root).Output()
			return strings.TrimSpace(string(raw)), e
		}
		revision, e := item("revision")
		if e != nil {
			return nil, errors.New("SVN checkout detected but host SVN identity unavailable")
		}
		uuid, e := item("repos-uuid")
		if e != nil {
			return nil, e
		}
		return map[string]string{"provider": "svn", "head": revision, "revision": revision, "repository_id": uuid, "working_copy_id": identityHash(root)}, nil
	}
	return vcs, nil
}
