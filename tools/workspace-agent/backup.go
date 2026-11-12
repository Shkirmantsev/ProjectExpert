package main

import (
	"archive/tar"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type Checkpoint struct {
	Schema     int             `json:"schema_version"`
	Product    string          `json:"product_version"`
	Generation string          `json:"generation"`
	Profile    string          `json:"embedding_profile"`
	Files      map[string]File `json:"files"`
}

func checkpointPath(name string) bool {
	if name == "" || strings.ContainsAny(name, "\\:\x00") || strings.HasPrefix(name, "/") {
		return false
	}
	for _, part := range strings.Split(name, "/") {
		if part == "" || part == "." || part == ".." {
			return false
		}
	}
	return true
}
func allowedCheckpoint(name string) bool {
	switch name {
	case "runtime.db", "embeddings.sqlite", "index.json", "wal.jsonl", "documents-v2.sqlite", "ingestion.json", "source-inventory.json", "workspace-index.json", "indexing-state.sqlite":
		return true
	}
	first := strings.Split(name, "/")[0]
	switch first {
	case "objects", "indexes", "runtime-state", "document-assets", "dense", "graph":
		return !strings.HasSuffix(name, "-wal") && !strings.HasSuffix(name, "-shm") && !strings.HasSuffix(name, ".tmp") && !strings.HasSuffix(name, ".lock")
	}
	return false
}
func verifyBackup(root string) (Checkpoint, error) {
	var m Checkpoint
	data, e := os.ReadFile(filepath.Join(root, "checkpoint-manifest.json"))
	if e != nil || len(data) > 16*1024*1024 {
		return m, errors.New("missing or oversized checkpoint manifest")
	}
	if e = json.Unmarshal(data, &m); e != nil {
		return m, e
	}
	if m.Schema != 1 || m.Product != "0.1.0" || m.Generation == "" || m.Profile == "" || len(m.Files) > 200000 {
		return m, errors.New("incompatible checkpoint")
	}
	var total int64
	for name, meta := range m.Files {
		if !checkpointPath(name) || !allowedCheckpoint(name) || meta.Size < 0 {
			return m, errors.New("unsafe backup entry")
		}
		path := filepath.Join(root, filepath.FromSlash(name))
		info, err := os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || info.Size() != meta.Size {
			return m, errors.New("backup size mismatch")
		}
		f, err := openSource(path)
		if err != nil {
			return m, err
		}
		h := sha256.New()
		_, err = io.Copy(h, f)
		f.Close()
		if err != nil || hex.EncodeToString(h.Sum(nil)) != meta.SHA {
			return m, errors.New("backup checksum mismatch")
		}
		total += meta.Size
		if total > 20*1024*1024*1024 {
			return m, errors.New("backup byte limit")
		}
	}
	bundlePath := filepath.Join(root, "runtime-state", "snapshot.json")
	if _, ok := m.Files["runtime-state/snapshot.json"]; !ok {
		return m, errors.New("checkpoint missing active snapshot")
	}
	bundleBytes, err := os.ReadFile(bundlePath)
	if err != nil {
		return m, err
	}
	var bundle struct {
		Active struct {
			Generation string `json:"active_index_generation"`
			Profile    string `json:"embedding_profile_identity"`
		} `json:"active"`
	}
	if err = json.Unmarshal(bundleBytes, &bundle); err != nil || bundle.Active.Generation != m.Generation || bundle.Active.Profile != m.Profile {
		return m, errors.New("checkpoint generation/profile mismatch")
	}
	e = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if path == root {
			return nil
		}
		if d.Type()&os.ModeSymlink != 0 {
			return errors.New("linked backup entry")
		}
		if d.IsDir() {
			return nil
		}
		rel, _ := filepath.Rel(root, path)
		name := filepath.ToSlash(rel)
		if name != "checkpoint-manifest.json" {
			if _, ok := m.Files[name]; !ok {
				return errors.New("unlisted backup file")
			}
		}
		return nil
	})
	return m, e
}
func extractBackup(stream io.Reader, root string) error {
	tr := tar.NewReader(stream)
	seen := map[string]bool{}
	var total int64
	for {
		h, e := tr.Next()
		if e == io.EOF {
			break
		}
		if e != nil {
			return e
		}
		if !checkpointPath(h.Name) || seen[h.Name] || h.Typeflag != tar.TypeReg || h.Size < 0 || len(seen) > 200000 {
			return errors.New("unsafe backup archive")
		}
		seen[h.Name] = true
		total += h.Size
		if total > 20*1024*1024*1024 || (h.Name == "checkpoint-manifest.json" && h.Size > 16*1024*1024) {
			return errors.New("backup byte limit")
		}
		target := filepath.Join(root, filepath.FromSlash(h.Name))
		if e = os.MkdirAll(filepath.Dir(target), 0700); e != nil {
			return e
		}
		f, e := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if e != nil {
			return e
		}
		_, e = io.Copy(f, tr)
		if e == nil {
			e = f.Sync()
		}
		f.Close()
		if e != nil {
			return e
		}
	}
	_, e := verifyBackup(root)
	if e != nil {
		return e
	}
	var dirs []string
	e = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			dirs = append(dirs, path)
		}
		return nil
	})
	if e != nil {
		return e
	}
	sort.Sort(sort.Reverse(sort.StringSlice(dirs)))
	for _, path := range dirs {
		if e = syncDirectory(path); e != nil {
			return e
		}
	}
	return nil
}
func runtimeArgs(c Config, write bool) []string {
	mode := ",readonly"
	if write {
		mode = ""
	}
	return []string{"--context", c.Context, "run", "--rm", "-i", "--network", "none", "--user", fmt.Sprintf("%d:%d", c.UID, c.GID),
		"--mount", "type=volume,src=" + c.Workspace + ",dst=/repo,readonly",
		"--mount", "type=volume,src=" + c.Runtime + ",dst=/repo/.project-intelligence-cache" + mode,
		"--entrypoint", "python", c.Image}
}
func activeGeneration(c Config) (string, error) {
	args := runtimeArgs(c, false)
	args = append(args, "-c", `import json,pathlib;p=pathlib.Path('/repo/.project-intelligence-cache/runtime-state/active-version.json'); print(json.loads(p.read_text()).get('active_index_generation','') if p.exists() else '')`)
	return command(args...)
}
func backupRoot(c Config) (string, error) {
	root := os.Getenv("PI_RUNTIME_BACKUP_DIR")
	if root == "" {
		root = filepath.Join(filepath.Dir(c.Repo), "ProjectExpert-backups", strings.TrimPrefix(c.Workspace, "projectexpert-workspace-"))
	}
	root, e := filepath.Abs(root)
	if e != nil {
		return "", e
	}
	if e = os.MkdirAll(root, 0700); e != nil {
		return "", e
	}
	resolved, e := filepath.EvalSymlinks(root)
	if e != nil {
		return "", e
	}
	rel, e := filepath.Rel(c.Repo, resolved)
	if e == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return "", errors.New("backup directory must be outside source repository")
	}
	return resolved, nil
}
func backup(c Config, kit string) (result error) {
	defer func() {
		if result != nil {
			var state map[string]any
			data, _ := os.ReadFile(filepath.Join(kit, "workspace-backup-status.json"))
			json.Unmarshal(data, &state)
			if state == nil {
				state = map[string]any{}
			}
			state["error"] = result.Error()
			state["last_attempt"] = time.Now().UTC()
			save(filepath.Join(kit, "workspace-backup-status.json"), state)
		}
	}()
	lock, e := operationLock(filepath.Join(kit, "workspace-operation.lock"))
	if e != nil {
		return e
	}
	defer lock.Close()
	return backupLocked(c, kit)
}
func backupLocked(c Config, kit string) error {
	if os.Getenv("PI_RUNTIME_BACKUP") == "off" {
		return nil
	}
	if e := pinned(c); e != nil {
		return e
	}
	root, e := backupRoot(c)
	if e != nil {
		return e
	}
	temporary, e := os.MkdirTemp(root, ".incomplete-")
	if e != nil {
		return e
	}
	defer os.RemoveAll(temporary)
	args := append(runtimeArgs(c, true), "-m", "pi_platform.adapters.runtime.runtime_checkpoint_export", "create", "--target", "/repo")
	cmd := exec.Command("docker", args...)
	cmd.Stderr = os.Stderr
	pipe, e := cmd.StdoutPipe()
	if e != nil {
		return e
	}
	if e = cmd.Start(); e != nil {
		return e
	}
	e = extractBackup(pipe, temporary)
	if e != nil {
		cmd.Process.Kill()
	}
	wait := cmd.Wait()
	if e != nil {
		return e
	}
	if wait != nil {
		return wait
	}
	m, e := verifyBackup(temporary)
	if e != nil {
		return e
	}
	name := time.Now().UTC().Format("20060102T150405.000000000Z") + "-" + identityHash(m.Generation)[:16]
	final := filepath.Join(root, name)
	if e = os.Rename(temporary, final); e != nil {
		return e
	}
	if e = syncDirectory(root); e != nil {
		return e
	}
	if e = save(filepath.Join(kit, "workspace-backup-status.json"), map[string]any{"last_backup": time.Now().UTC(), "generation": m.Generation, "path": final}); e != nil {
		return e
	}
	// Host acknowledgment follows verification and the final rename.
	ack := append(runtimeArgs(c, true), "-c", `from pathlib import Path; from pi_platform.core.runtime.runtime_checkpoint import atomic_json; import datetime; atomic_json(Path('/repo/.project-intelligence-cache/checkpoint-status.json'), {'last_backup':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':None,'state':'host-verified'})`)
	if _, e = command(ack...); e != nil {
		return e
	}
	// Retention only prunes verified completed generations, preserving newest good.
	entries, _ := os.ReadDir(root)
	var valid []string
	for _, entry := range entries {
		if entry.IsDir() && !strings.HasPrefix(entry.Name(), ".") {
			path := filepath.Join(root, entry.Name())
			if _, err := verifyBackup(path); err == nil {
				valid = append(valid, path)
			}
		}
	}
	sort.Strings(valid)
	var total int64
	for _, path := range valid {
		m, _ := verifyBackup(path)
		for _, f := range m.Files {
			total += f.Size
		}
	}
	for len(valid) > 1 && (len(valid) > 3 || total > 40*1024*1024*1024) {
		m, _ := verifyBackup(valid[0])
		for _, f := range m.Files {
			total -= f.Size
		}
		if e = os.RemoveAll(valid[0]); e != nil {
			return e
		}
		valid = valid[1:]
	}
	return nil
}
func restore(c Config, kit, source string) error {
	if source == "" {
		return errors.New("restore requires --backup PATH and stopped application")
	}
	if e := pinned(c); e != nil {
		return e
	}
	source, e := filepath.Abs(source)
	if e != nil {
		return e
	}
	if _, e = verifyBackup(source); e != nil {
		return e
	}
	running, e := command("--context", c.Context, "ps", "-q", "--filter", "volume="+c.Workspace)
	if e != nil {
		return e
	}
	if running != "" {
		return errors.New("stop application and supervisor before restore")
	}
	if f, err := supervisorLock(filepath.Join(kit, "workspace-supervisor.lock")); err != nil {
		return errors.New("stop supervisor before restore")
	} else {
		defer f.Close()
	}
	selected := c.Runtime + "-restore-" + time.Now().UTC().Format("20060102150405")
	if _, e = command("--context", c.Context, "volume", "create", selected); e != nil {
		return e
	}
	args := []string{"--context", c.Context, "run", "--rm", "-i", "--network", "none", "--mount", "type=volume,src=" + selected + ",dst=/inactive", "--entrypoint", "python", c.Image, "-m", "pi_platform.adapters.runtime.runtime_checkpoint_export", "restore", "--inactive-root", "/inactive"}
	cmd := exec.Command("docker", args...)
	cmd.Stderr = os.Stderr
	pipe, e := cmd.StdinPipe()
	if e != nil {
		return e
	}
	if e = cmd.Start(); e != nil {
		return e
	}
	tw := tar.NewWriter(pipe)
	e = filepath.WalkDir(source, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		rel, _ := filepath.Rel(source, path)
		info, err := d.Info()
		if err != nil {
			return err
		}
		if err = tw.WriteHeader(&tar.Header{Name: filepath.ToSlash(rel), Mode: 0600, Size: info.Size()}); err != nil {
			return err
		}
		f, err := openSource(path)
		if err != nil {
			return err
		}
		defer f.Close()
		_, err = io.Copy(tw, f)
		return err
	})
	closeErr := tw.Close()
	pipe.Close()
	wait := cmd.Wait()
	if e != nil {
		return e
	}
	if closeErr != nil {
		return closeErr
	}
	if wait != nil {
		return wait
	}
	c.Runtime = selected
	if e = save(filepath.Join(kit, "workspace-agent.json"), c); e != nil {
		return e
	}
	if e = writeWorkspaceEnv(c, kit); e != nil {
		return e
	}
	fmt.Println("Restored into inactive volume", selected, "; previous runtime preserved. Start normally to validate/rebuild readiness.")
	return nil
}
