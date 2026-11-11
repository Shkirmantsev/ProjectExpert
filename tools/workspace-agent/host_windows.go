package main

import (
	"encoding/binary"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unicode/utf16"
	"unsafe"
)

func owners(path string) (int, int) { return 1000, 1000 }
func reparse(info os.FileInfo) bool {
	v, ok := info.Sys().(*syscall.Win32FileAttributeData)
	return ok && v.FileAttributes&syscall.FILE_ATTRIBUTE_REPARSE_POINT != 0
}

func windowsDOSPath(path string) string {
	if strings.HasPrefix(path, `\\?\UNC\`) {
		return `\\` + strings.TrimPrefix(path, `\\?\UNC\`)
	}
	return strings.TrimPrefix(path, `\\?\`)
}

func openSource(path string) (*os.File, error) {
	p, e := syscall.UTF16PtrFromString(path)
	if e != nil {
		return nil, e
	}
	h, e := syscall.CreateFile(p, syscall.GENERIC_READ, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(h), path)
	info, e := f.Stat()
	if e != nil || reparse(info) {
		f.Close()
		return nil, os.ErrPermission
	}
	proc := syscall.NewLazyDLL("kernel32.dll").NewProc("GetFinalPathNameByHandleW")
	buffer := make([]uint16, 32768)
	n, _, _ := proc.Call(uintptr(h), uintptr(unsafe.Pointer(&buffer[0])), uintptr(len(buffer)), 0)
	if n == 0 || n >= uintptr(len(buffer)) {
		f.Close()
		return nil, os.ErrPermission
	}
	final := windowsDOSPath(syscall.UTF16ToString(buffer[:n]))
	absolute, err := filepath.Abs(path)
	if err != nil {
		f.Close()
		return nil, err
	}
	// Windows temp roots can contain 8.3 aliases (e.g. RUNNER~1). Expand
	// their spelling before comparing with the normalized handle path. Unlike
	// EvalSymlinks, GetLongPathName does not resolve a junction/symlink parent:
	// that redirection must still cause the final-path comparison to fail.
	expected, err := syscall.UTF16PtrFromString(absolute)
	if err != nil {
		f.Close()
		return nil, err
	}
	long := make([]uint16, 32768)
	length, err := syscall.GetLongPathName(expected, &long[0], uint32(len(long)))
	if err != nil || length == 0 || length >= uint32(len(long)) ||
		!strings.EqualFold(filepath.Clean(final), filepath.Clean(windowsDOSPath(syscall.UTF16ToString(long[:length])))) {
		f.Close()
		return nil, os.ErrPermission
	}
	var identity syscall.ByHandleFileInformation
	if err = syscall.GetFileInformationByHandle(h, &identity); err != nil || identity.NumberOfLinks != 1 {
		f.Close()
		return nil, os.ErrPermission
	}
	return f, nil
}

// ReadDirectoryChangesW is recursive; overflow still wakes a full reconciliation.
func watch(root, omit string) <-chan bool {
	out := make(chan bool, 1)
	p, e := syscall.UTF16PtrFromString(root)
	if e != nil {
		return out
	}
	h, e := syscall.CreateFile(p, 0x0001, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS, 0)
	if e != nil {
		return out
	}
	proc := syscall.NewLazyDLL("kernel32.dll").NewProc("ReadDirectoryChangesW")
	go func() {
		defer syscall.CloseHandle(h)
		buf := make([]byte, 65536)
		for {
			var n uint32
			r, _, _ := proc.Call(uintptr(h), uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)), 1, 0x0000001f, uintptr(unsafe.Pointer(&n)), 0, 0)
			if r == 0 {
				return
			}
			relevant := n == 0
			for offset := uint32(0); offset+12 <= n; {
				next := binary.LittleEndian.Uint32(buf[offset:])
				length := binary.LittleEndian.Uint32(buf[offset+8:])
				if offset+12+length > n {
					relevant = true
					break
				}
				units := make([]uint16, length/2)
				for i := range units {
					units[i] = binary.LittleEndian.Uint16(buf[offset+12+uint32(i*2):])
				}
				name := strings.ReplaceAll(string(utf16.Decode(units)), "\\", "/")
				if eventRelevant(root, omit, name) {
					relevant = true
				}
				if next == 0 {
					break
				}
				offset += next
			}
			if !relevant {
				continue
			}
			select {
			case out <- true:
			default:
			}
		}
	}()
	return out
}

func supervisorLock(path string) (*os.File, error) {
	p, e := syscall.UTF16PtrFromString(path)
	if e != nil {
		return nil, e
	}
	h, e := syscall.CreateFile(p, syscall.GENERIC_READ|syscall.GENERIC_WRITE, 0, nil, syscall.OPEN_ALWAYS, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if e != nil {
		return nil, errors.New("supervisor already active")
	}
	return os.NewFile(uintptr(h), path), nil
}

func operationLock(path string) (*os.File, error) {
	for i := 0; i < 1200; i++ {
		if f, e := supervisorLock(path); e == nil {
			return f, nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return nil, errors.New("workspace operation lock timed out")
}

// Directory FlushFileBuffers is not portable on Windows. NTFS metadata durability
// remains a native platform acceptance gate, not a claim from cross-compilation.
func syncDirectory(path string) error { return nil }
