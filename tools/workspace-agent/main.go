// Host-native bounded scanner and Docker archive transport. No runtime dependencies.
package main

import (
	"archive/tar"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type File struct {
	Size int64  `json:"size"`
	SHA  string `json:"sha256"`
}
type Manifest struct {
	Schema     int               `json:"schema_version"`
	Generation string            `json:"generation"`
	Files      map[string]File   `json:"files"`
	VCS        map[string]string `json:"vcs"`
}
type Config struct {
	Repo, Context, Workspace, Runtime, Image string
	Endpoint                                 string
	UID, GID                                 int
}

func command(args ...string) (string, error) {
	b, e := exec.Command("docker", args...).CombinedOutput()
	if e != nil {
		return "", fmt.Errorf("docker operation failed: %w", e)
	}
	return strings.TrimSpace(string(b)), nil
}
func contextName() (string, error) { return command("context", "show") }
func excluded(name string) bool {
	name = filepath.ToSlash(name)
	if name == "tmp/local" || strings.HasPrefix(name, "tmp/local/") || name == "distribution/sbom" || strings.HasPrefix(name, "distribution/sbom/") {
		return true
	}
	for _, part := range strings.Split(filepath.ToSlash(name), "/") {
		p := strings.ToLower(part)
		switch p {
		case ".git", ".svn", ".hg", ".projectexpert-workspace", "project-knowledge", ".project-intelligence-cache", ".project-intelligence-deploy", "node_modules", "__pycache__", ".venv", "venv", "target", "build", "dist", "out", ".next", "vendor", "third_party", "generated", ".generated", "credentials", "credentials.json", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".ssh", ".aws", ".azure", ".kube", ".docker", ".npmrc", ".pypirc", ".netrc", ".git-credentials":
			return true
		}
		if strings.HasPrefix(p, ".env") || strings.HasSuffix(p, ".pem") || strings.HasSuffix(p, ".key") || strings.HasSuffix(p, ".p12") || strings.HasSuffix(p, ".pfx") {
			return true
		}
	}
	return false
}
func scan(root string, omit ...string) (Manifest, error) {
	policy, policyErr := loadPolicy(root)
	if policyErr != nil {
		return Manifest{}, policyErr
	}
	m := Manifest{Schema: 1, Files: map[string]File{}, VCS: map[string]string{"provider": "none"}}
	var total int64
	seen := map[string]bool{}
	err := filepath.WalkDir(root, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if path == root {
			return nil
		}
		for _, skip := range omit {
			if path == skip {
				if d.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}
		}
		name, e := filepath.Rel(root, path)
		if e != nil {
			return e
		}
		name = filepath.ToSlash(name)
		if excluded(name) || policy.excludes(name, d.IsDir()) {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if d.Type()&os.ModeSymlink != 0 {
			return nil
		}
		info, e := d.Info()
		if e != nil {
			return e
		}
		if reparse(info) {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if !info.Mode().IsRegular() {
			if d.IsDir() {
				return nil
			}
			return errors.New("special source file")
		}
		if reparse(info) {
			return errors.New("reparse source file")
		}
		if info.Size() > policy.maxFile {
			return nil
		}
		if len(m.Files) >= 200000 {
			return errors.New("file limit")
		}
		total += info.Size()
		if total > 20*1024*1024*1024 {
			return errors.New("byte limit")
		}
		key := strings.ToLower(name)
		if seen[key] {
			return errors.New("case collision")
		}
		seen[key] = true
		if hash, ok := cached(path, info.Size(), info.ModTime().UnixNano()); ok {
			m.Files[name] = File{info.Size(), hash}
			return nil
		}
		f, e := openSource(path)
		if e != nil {
			return e
		}
		h := sha256.New()
		_, e = io.Copy(h, io.LimitReader(f, info.Size()+1))
		after, se := f.Stat()
		f.Close()
		if e != nil {
			return e
		}
		if se != nil || after.Size() != info.Size() || !after.ModTime().Equal(info.ModTime()) {
			return errors.New("source changed during scan")
		}
		hash := hex.EncodeToString(h.Sum(nil))
		m.Files[name] = File{info.Size(), hash}
		hashCache[path] = cachedHash{info.Size(), info.ModTime().UnixNano(), hash, time.Now().Unix()}
		return nil
	})
	if err != nil {
		return m, err
	}
	m.VCS, err = hostVCS(root)
	if err != nil {
		return m, err
	}
	b, _ := json.Marshal(struct {
		Files map[string]File
		VCS   map[string]string
	}{m.Files, m.VCS})
	h := sha256.Sum256(b)
	m.Generation = hex.EncodeToString(h[:])
	return m, nil
}
func save(path string, v any) error {
	data, e := json.MarshalIndent(v, "", "  ")
	if e != nil {
		return e
	}
	return saveBytes(path, data)
}
func saveBytes(path string, data []byte) error {
	f, e := os.CreateTemp(filepath.Dir(path), ".workspace-write-")
	if e != nil {
		return e
	}
	temporary := f.Name()
	defer os.Remove(temporary)
	if _, e = f.Write(data); e != nil {
		f.Close()
		return e
	}
	if e = f.Sync(); e != nil {
		f.Close()
		return e
	}
	if e = f.Close(); e != nil {
		return e
	}
	if e = os.Rename(temporary, path); e != nil {
		return e
	}
	return syncDirectory(filepath.Dir(path))
}
func readConfig(kit string) (Config, error) {
	var c Config
	b, e := os.ReadFile(filepath.Join(kit, "workspace-agent.json"))
	if e == nil {
		e = json.Unmarshal(b, &c)
	}
	return c, e
}
func pinned(c Config) error {
	n, e := contextName()
	if e != nil {
		return e
	}
	endpoint, err := command("context", "inspect", c.Context, "--format", "{{.Endpoints.docker.Host}}")
	if err != nil || endpoint != c.Endpoint {
		return errors.New("Docker endpoint changed; refusing transfer")
	}
	if n != c.Context {
		return errors.New("Docker context changed; refusing transfer")
	}
	return nil
}
func prepare(repo, kit string) error {
	ctx, e := contextName()
	if e != nil {
		return e
	}
	endpoint, e := command("context", "inspect", ctx, "--format", "{{.Endpoints.docker.Host}}")
	if e != nil {
		return e
	}
	if !strings.HasPrefix(endpoint, "unix://") && !strings.HasPrefix(endpoint, "npipe://") {
		return errors.New("only local Docker endpoints are allowed")
	}
	kind, e := command("--context", ctx, "info", "--format", "{{.OSType}}")
	if e != nil || kind != "linux" {
		return errors.New("Linux Docker engine required")
	}
	hash := sha256.Sum256([]byte(repo + "\x00" + ctx + "\x00" + endpoint))
	id := hex.EncodeToString(hash[:12])
	image := configuredImage(kit)
	if image == "" {
		return errors.New("PI_IMAGE required in environment or kit deployment.env")
	}
	if strings.ContainsAny(repo+image, "\r\n"+string(rune(39))+string(rune(34))) {
		return errors.New("invalid configuration")
	}
	if e = os.MkdirAll(filepath.Join(repo, "project-knowledge"), 0755); e != nil {
		return e
	}
	uid, gid := owners(repo)
	c := Config{Repo: repo, Context: ctx, Endpoint: endpoint, Workspace: "projectexpert-workspace-" + id, Runtime: "projectexpert-runtime-" + id, Image: image, UID: uid, GID: gid}
	if e = os.MkdirAll(kit, 0700); e != nil {
		return e
	}
	if previous, err := readConfig(kit); err == nil {
		if previous.Repo != repo || previous.Context != ctx || previous.Endpoint != endpoint || previous.Image != image {
			if guard, lockErr := supervisorLock(filepath.Join(kit, "workspace-supervisor.lock")); lockErr != nil {
				return errors.New("stop the existing workspace supervisor before changing project, context or image")
			} else {
				guard.Close()
			}
		}
		if previous.Repo == repo && previous.Context == ctx && previous.Endpoint == endpoint {
			c.Runtime = previous.Runtime
		}
	}
	if e = mountPreflight(&c); e != nil {
		return e
	}
	if e = save(filepath.Join(kit, "workspace-agent.json"), c); e != nil {
		return e
	}
	return writeWorkspaceEnv(c, kit)
}
func writeWorkspaceEnv(c Config, kit string) error {
	env := fmt.Sprintf("PI_WORKSPACE_MODE=volume\nPI_WORKSPACE_VOLUME=%s\nPI_RUNTIME_VOLUME=%s\nPI_CANONICAL_HOST_DIR='%s'\nPI_WORKSPACE_CONTEXT=%s\n", c.Workspace, c.Runtime, filepath.ToSlash(filepath.Join(c.Repo, "project-knowledge")), c.Context)
	return saveBytes(filepath.Join(kit, "workspace.env"), []byte(env))
}
func syncRepo(c Config, kit string) error {
	lock, e := operationLock(filepath.Join(kit, "workspace-operation.lock"))
	if e != nil {
		return e
	}
	defer lock.Close()
	return syncRepoLocked(c, kit)
}
func syncRepoLocked(c Config, kit string) error {
	if e := pinned(c); e != nil {
		return e
	}
	if !cacheLoaded {
		cacheLoaded = true
		b, _ := os.ReadFile(filepath.Join(kit, "workspace-hash-cache.json"))
		json.Unmarshal(b, &hashCache)
		if hashCache == nil {
			hashCache = map[string]cachedHash{}
		}
	}
	m, e := scan(c.Repo, kit)
	if e != nil {
		return e
	}
	confirm, err := scan(c.Repo, kit)
	if err != nil {
		return err
	}
	if confirm.Generation != m.Generation {
		return errors.New("source changed during reconciliation; retry")
	}
	var old Manifest
	for _, v := range []string{c.Workspace, c.Runtime} {
		if _, e = command("--context", c.Context, "volume", "create", v); e != nil {
			return e
		}
	}
	// Receiver owns the applied manifest; host state is only a cache.
	raw, err := command("--context", c.Context, "run", "--rm", "--network", "none", "--mount", "type=volume,src="+c.Workspace+",dst=/repo,readonly", "--entrypoint", "python", c.Image, "-c", `import pathlib; p=pathlib.Path('/repo/.projectexpert-workspace/applied-generation.json');print(p.read_text() if p.exists() else '{}')`)
	if err != nil {
		return err
	}
	if err = json.Unmarshal([]byte(raw), &old); err != nil {
		return err
	}
	args := []string{"--context", c.Context, "run", "--rm", "-i", "--network", "none", "--mount", "type=volume,src=" + c.Workspace + ",dst=/repo", "--entrypoint", "python", c.Image, "-m", "pi_platform.adapters.sync.workspace_importer", "--owner-uid", fmt.Sprint(c.UID), "--owner-gid", fmt.Sprint(c.GID)}
	cmd := exec.Command("docker", args...)
	stdin, e := cmd.StdinPipe()
	if e != nil {
		return e
	}
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if e = cmd.Start(); e != nil {
		return e
	}
	tw := tar.NewWriter(stdin)
	data, _ := json.Marshal(m)
	e = tw.WriteHeader(&tar.Header{Name: "manifest.json", Mode: 0600, Size: int64(len(data))})
	if e == nil {
		_, e = tw.Write(data)
	}
	var bytes int64
	for name, meta := range m.Files {
		if e != nil {
			break
		}
		if old.Files[name] == meta {
			continue
		}
		path := filepath.Join(c.Repo, filepath.FromSlash(name))
		info, err := os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || reparse(info) {
			e = errors.New("source changed before transfer")
			break
		}
		f, err := openSource(path)
		if err != nil {
			e = err
			break
		}
		e = tw.WriteHeader(&tar.Header{Name: name, Mode: 0644, Size: meta.Size})
		if e == nil {
			var n int64
			n, e = io.Copy(tw, io.LimitReader(f, meta.Size+1))
			bytes += n
		}
		f.Close()
	}
	closeErr := tw.Close()
	stdin.Close()
	waitErr := cmd.Wait()
	if e != nil {
		return e
	}
	if closeErr != nil {
		return closeErr
	}
	if waitErr != nil {
		os.Remove(filepath.Join(kit, "workspace-manifest.json"))
		return waitErr
	}
	save(filepath.Join(kit, "workspace-hash-cache.json"), hashCache)
	if e = save(filepath.Join(kit, "workspace-manifest.json"), m); e != nil {
		return e
	}
	return save(filepath.Join(kit, "workspace-status.json"), map[string]any{"generation": m.Generation, "transferred_bytes": bytes, "last_sync": time.Now().UTC(), "pending_files": 0})
}
func run() error {
	if len(os.Args) < 2 {
		return errors.New("expected prepare, sync, supervise, stop, status")
	}
	action := os.Args[1]
	fs := flag.NewFlagSet(action, flag.ContinueOnError)
	backupPath := fs.String("backup", "", "verified host snapshot for explicit inactive restore")
	repo := fs.String("repo", "", "host repository")
	kit := fs.String("kit", "", "deployment kit")
	if e := fs.Parse(os.Args[2:]); e != nil {
		return e
	}
	if *repo == "" || *kit == "" {
		return errors.New("--repo and --kit required")
	}
	r, e := filepath.Abs(*repo)
	if e != nil {
		return e
	}
	k, e := filepath.Abs(*kit)
	if e != nil {
		return e
	}
	if action == "prepare" {
		return prepare(r, k)
	}
	c, e := readConfig(k)
	if e != nil {
		return e
	}
	if c.Repo != r {
		return errors.New("repository identity mismatch")
	}
	switch action {
	case "sync":
		return syncRepo(c, k)
	case "context":
		if e = pinned(c); e != nil {
			return e
		}
		if e = writeWorkspaceEnv(c, k); e != nil {
			return e
		}
		fmt.Println(c.Context)
		return nil
	case "backup":
		return backup(c, k)
	case "restore":
		return restore(c, k, *backupPath)
	case "status":
		b, e := os.ReadFile(filepath.Join(k, "workspace-status.json"))
		if e != nil {
			return e
		}
		var status map[string]any
		if e = json.Unmarshal(b, &status); e != nil {
			return e
		}
		if raw, err := os.ReadFile(filepath.Join(k, "workspace-backup-status.json")); err == nil {
			var backupState any
			if json.Unmarshal(raw, &backupState) == nil {
				status["backup"] = backupState
			}
		}
		output, e := json.MarshalIndent(status, "", "  ")
		if e != nil {
			return e
		}
		fmt.Println(string(output))
		return nil
	case "stop":
		if e = os.WriteFile(filepath.Join(k, "workspace-stop"), []byte("stop"), 0600); e != nil {
			return e
		}
		deadline := time.Now().Add(120 * time.Second)
		for time.Now().Before(deadline) {
			if f, err := supervisorLock(filepath.Join(k, "workspace-supervisor.lock")); err == nil {
				f.Close()
				return nil
			}
			time.Sleep(100 * time.Millisecond)
		}
		return errors.New("supervisor stop pending; active operation did not finish within 120 seconds")
	case "supervise":
		lock := filepath.Join(k, "workspace-supervisor.lock")
		f, e := supervisorLock(lock)
		if e != nil {
			return e
		}
		defer f.Close()
		os.Remove(filepath.Join(k, "workspace-stop"))
		backoff := time.Second
		lastBackup := time.Time{}
		lastGeneration := ""
		events := watch(c.Repo, k)
		for {
			if _, e := os.Stat(filepath.Join(k, "workspace-stop")); e == nil {
				return nil
			}
			e = syncRepo(c, k)
			if e != nil {
				save(filepath.Join(k, "workspace-status.json"), map[string]string{"error": e.Error()})
				time.Sleep(backoff)
				if backoff < 30*time.Second {
					backoff *= 2
				}
			} else {
				backoff = time.Second
				if os.Getenv("PI_RUNTIME_BACKUP") != "off" {
					generation, err := activeGeneration(c)
					interval := 30 * time.Minute
					if raw := os.Getenv("PI_RUNTIME_BACKUP_INTERVAL_MINUTES"); raw != "" {
						if minutes, err := time.ParseDuration(raw + "m"); err == nil && minutes >= time.Minute {
							interval = minutes
						}
					}
					if err == nil && generation != "" && (generation != lastGeneration || time.Since(lastBackup) >= interval) && time.Since(lastBackup) >= time.Minute {
						if err = backup(c, k); err != nil {
							fmt.Fprintln(os.Stderr, "Runtime backup pending:", err)
						} else {
							lastGeneration = generation
							lastBackup = time.Now()
						}
					}
				}
				select {
				case <-events:
					hashCache = map[string]cachedHash{}
					time.Sleep(debounceInterval())
				case <-time.After(5 * time.Second):
				}
			}
		}
	default:
		return errors.New("unknown action")
	}
}
func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}

func eventRelevant(root, omit, name string) bool {
	full := filepath.Join(root, filepath.FromSlash(name))
	if full == omit || strings.HasPrefix(full, omit+string(os.PathSeparator)) {
		return false
	}
	return !excluded(filepath.ToSlash(name))
}

func configuredImage(kit string) string {
	image := os.Getenv("PI_IMAGE")
	if image != "" {
		return image
	}
	data, _ := os.ReadFile(filepath.Join(kit, "deployment.env"))
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "PI_IMAGE=") {
			image = strings.Trim(strings.TrimSpace(strings.TrimPrefix(line, "PI_IMAGE=")), "\"'")
		}
	}
	return image
}
