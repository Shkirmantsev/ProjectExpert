package main

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
)

func mountPreflight(c *Config) error {
	real, e := filepath.EvalSymlinks(c.Repo)
	if e != nil {
		return e
	}
	if filepath.Clean(real) != filepath.Clean(c.Repo) {
		return errors.New("linked repository root unsupported")
	}
	canonical := filepath.Join(c.Repo, "project-knowledge")
	real, e = filepath.EvalSymlinks(canonical)
	if e != nil {
		return e
	}
	if filepath.Clean(real) != filepath.Clean(canonical) {
		return errors.New("linked canonical directory unsupported")
	}
	entropy := make([]byte, 16)
	if _, e = rand.Read(entropy); e != nil {
		return e
	}
	token := hex.EncodeToString(entropy)
	name := ".projectexpert-probe-" + token
	path := filepath.Join(canonical, name)
	if e = os.WriteFile(path, []byte(token), 0600); e != nil {
		return e
	}
	defer os.Remove(path)
	// Verify the actual host directory, image capability and least-privilege write.
	script := `import os,pathlib,sys; import pi_platform.adapters.sync.workspace_importer; import pi_platform.adapters.runtime.runtime_checkpoint_export; p=pathlib.Path('/canonical')/sys.argv[1]; assert p.read_text()==sys.argv[2]; f=p.open('w');f.write('ack:'+sys.argv[2]);f.flush();os.fsync(f.fileno());f.close()`
	args := []string{"--context", c.Context, "run", "--rm", "--network", "none", "--user", fmt.Sprintf("%d:%d", c.UID, c.GID), "--mount", "type=bind,src=" + canonical + ",dst=/canonical", "--entrypoint", "python", c.Image, "-c", script, name, token}
	if _, e = command(args...); e != nil {
		return errors.New("canonical write-through or application compatibility preflight failed")
	}
	data, e := os.ReadFile(path)
	if e != nil || string(data) != "ack:"+token {
		return errors.New("canonical mount identity mismatch")
	}
	return nil
}
