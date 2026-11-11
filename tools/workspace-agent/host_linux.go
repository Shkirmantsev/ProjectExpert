package main

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

func owners(path string) (int, int) {
	s, e := os.Stat(path)
	if e == nil {
		if v, ok := s.Sys().(*syscall.Stat_t); ok {
			return int(v.Uid), int(v.Gid)
		}
	}
	return os.Getuid(), os.Getgid()
}
func reparse(info os.FileInfo) bool { return false }

func openSource(path string) (*os.File, error) {
	absolute, e := filepath.Abs(path)
	if e != nil {
		return nil, e
	}
	fd, e := syscall.Open("/", syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_CLOEXEC, 0)
	if e != nil {
		return nil, e
	}
	parts := strings.Split(strings.TrimPrefix(absolute, "/"), "/")
	for i, part := range parts {
		flags := syscall.O_RDONLY | syscall.O_NOFOLLOW | syscall.O_CLOEXEC | syscall.O_NONBLOCK
		if i < len(parts)-1 {
			flags |= syscall.O_DIRECTORY
		}
		next, err := syscall.Openat(fd, part, flags, 0)
		syscall.Close(fd)
		if err != nil {
			return nil, err
		}
		fd = next
	}
	var st syscall.Stat_t
	if e = syscall.Fstat(fd, &st); e != nil || st.Mode&syscall.S_IFMT != syscall.S_IFREG || st.Nlink != 1 {
		syscall.Close(fd)
		return nil, errors.New("unsafe source file")
	}
	return os.NewFile(uintptr(fd), path), nil
}

func supervisorLock(path string) (*os.File, error) {
	f, e := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
	if e != nil {
		return nil, e
	}
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return nil, errors.New("supervisor already active")
	}
	return f, nil
}

// Watch hints accelerate existing directories; periodic reconciliation covers overflow/new subtrees.
func watch(root, omit string) <-chan bool {
	out := make(chan bool, 1)
	fd, e := syscall.InotifyInit1(syscall.IN_CLOEXEC)
	if e != nil {
		return out
	}
	filepath.WalkDir(root, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return nil
		}
		rel, _ := filepath.Rel(root, path)
		if path == omit || (path != root && excluded(filepath.ToSlash(rel))) {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if d.IsDir() {
			syscall.InotifyAddWatch(fd, path, syscall.IN_CLOSE_WRITE|syscall.IN_CREATE|syscall.IN_DELETE|syscall.IN_MOVED_FROM|syscall.IN_MOVED_TO|syscall.IN_ATTRIB)
		}
		return nil
	})
	go func() {
		defer syscall.Close(fd)
		buf := make([]byte, 65536)
		for {
			n, e := syscall.Read(fd, buf)
			if e != nil || n == 0 {
				return
			}
			select {
			case out <- true:
			default:
			}
		}
	}()
	return out
}

func operationLock(path string) (*os.File, error) {
	f, e := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
	if e != nil {
		return nil, e
	}
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX); e != nil {
		f.Close()
		return nil, e
	}
	return f, nil
}

func syncDirectory(path string) error {
	f, e := os.Open(path)
	if e != nil {
		return e
	}
	defer f.Close()
	return f.Sync()
}
