package main

import (
	"bufio"
	"crypto/md5"
	"embed"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	appName    = "Atlas Tools Label Sheet Builder"
	appVersion = "1.3.1"
	pythonURL  = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
	pythonMD5  = "fe8ef205f2e9c3ba44d0cf9954e1abd3"
)

//go:embed app_bundle.zip
var embeddedFiles embed.FS

var (
	user32          = syscall.NewLazyDLL("user32.dll")
	procMessageBoxW = user32.NewProc("MessageBoxW")
)

func messageBox(title, text string, flags uintptr) {
	titlePtr, _ := syscall.UTF16PtrFromString(title)
	textPtr, _ := syscall.UTF16PtrFromString(text)
	procMessageBoxW.Call(0, uintptr(unsafe.Pointer(textPtr)), uintptr(unsafe.Pointer(titlePtr)), flags)
}

func fail(err error) {
	messageBox(appName, "The application could not start.\n\n"+err.Error(), 0x10) // MB_ICONERROR
	os.Exit(1)
}

func main() {
	root, err := dataRoot()
	if err != nil {
		fail(err)
	}
	for _, dir := range []string{root, filepath.Join(root, "Templates"), filepath.Join(root, "Backups"), filepath.Join(root, "Temp")} {
		if err := os.MkdirAll(dir, 0755); err != nil {
			fail(fmt.Errorf("could not create the application data folders: %w", err))
		}
	}

	payload, err := embeddedFiles.ReadFile("app_bundle.zip")
	if err != nil { fail(fmt.Errorf("embedded application files are unavailable: %w", err)) }
	appDir, err := installApplication(root, appVersion, payload)
	if err != nil { fail(err) }

	runtimeDir := filepath.Join(root, "Runtime")
	firstRuntimeInstall := false
	if _, err := os.Stat(filepath.Join(runtimeDir, "python.exe")); errors.Is(err, os.ErrNotExist) {
		firstRuntimeInstall = true
		messageBox(
			appName,
			"First-launch setup will now install the program's private PDF engine.\n\nNo separate software installation is required. This normally takes less than a minute and only happens once. An internet connection is required for this first launch.",
			0x40, // MB_ICONINFORMATION
		)
	}
	if err := ensurePythonRuntime(runtimeDir, root); err != nil {
		fail(err)
	}

	if firstRuntimeInstall {
		messageBox(appName, "Setup is complete. The Label Sheet Builder will now open.", 0x40)
	}

	if err := runApplication(root, appDir, runtimeDir); err != nil {
		fail(err)
	}
}

func dataRoot() (string, error) {
	base := os.Getenv("LOCALAPPDATA")
	if strings.TrimSpace(base) == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		base = filepath.Join(home, "AppData", "Local")
	}
	return filepath.Join(base, "Atlas Tools Label Maker"), nil
}

func ensurePythonRuntime(runtimeDir, root string) error {
	pythonExe := filepath.Join(runtimeDir, "python.exe")
	if _, err := os.Stat(pythonExe); err == nil {
		return configurePythonPath(runtimeDir)
	}

	_ = os.RemoveAll(runtimeDir)
	if err := os.MkdirAll(runtimeDir, 0755); err != nil {
		return err
	}
	zipPath := filepath.Join(root, "Temp", "python-runtime.zip")
	_ = os.Remove(zipPath)
	if err := downloadFile(pythonURL, zipPath); err != nil {
		return fmt.Errorf("could not download the private PDF engine. Check the internet connection and try again.\n\n%w", err)
	}
	defer os.Remove(zipPath)

	if err := verifyRuntimeArchive(zipPath); err != nil {
		return err
	}
	if err := extractZipFile(zipPath, runtimeDir); err != nil {
		return fmt.Errorf("could not install the private PDF engine: %w", err)
	}
	if _, err := os.Stat(pythonExe); err != nil {
		return errors.New("the private PDF engine installation was incomplete")
	}
	return configurePythonPath(runtimeDir)
}

func configurePythonPath(runtimeDir string) error {
	candidates, _ := filepath.Glob(filepath.Join(runtimeDir, "python*._pth"))
	if len(candidates) == 0 {
		return errors.New("the private PDF engine configuration file is missing")
	}
	zipName := "python312.zip"
	if _, err := os.Stat(filepath.Join(runtimeDir, zipName)); err != nil {
		matches, _ := filepath.Glob(filepath.Join(runtimeDir, "python*.zip"))
		if len(matches) == 0 {
			return errors.New("the private PDF engine standard library is missing")
		}
		zipName = filepath.Base(matches[0])
	}
	content := strings.Join([]string{
		zipName,
		".",
		"import site",
		"",
	}, "\r\n")
	if current, err := os.ReadFile(candidates[0]); err == nil && string(current) == content { return nil }
	return os.WriteFile(candidates[0], []byte(content), 0644)
}

func downloadFile(url, target string) error {
	client := &http.Client{Timeout: 12 * time.Minute}
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", appName+"/"+appVersion)
	response, err := client.Do(req)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("download server returned %s", response.Status)
	}
	temp := target + ".part"
	file, err := os.Create(temp)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(file, response.Body)
	closeErr := file.Close()
	if copyErr != nil {
		_ = os.Remove(temp)
		return copyErr
	}
	if closeErr != nil {
		_ = os.Remove(temp)
		return closeErr
	}
	return os.Rename(temp, target)
}

func verifyRuntimeArchive(path string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	stat, err := file.Stat()
	if err != nil {
		return err
	}
	// A size range catches HTML error pages while allowing the canonical and alias packages.
	if stat.Size() < 10_000_000 || stat.Size() > 13_000_000 {
		return errors.New("the downloaded PDF engine package has an unexpected size")
	}
	hash := md5.New() // Python.org publishes this package checksum on the release page.
	if _, err := io.Copy(hash, file); err != nil {
		return err
	}
	got := hex.EncodeToString(hash.Sum(nil))
	if got != pythonMD5 {
		return fmt.Errorf("the downloaded PDF engine package failed its integrity check (received %s)", got)
	}
	return nil
}

func runApplication(root, appDir, runtimeDir string) error {
	pythonExe := filepath.Join(runtimeDir, "python.exe")
	script := filepath.Join(appDir, "atlas_label_maker.py")
	command := exec.Command(pythonExe, "-c", pythonBootstrap, script, "--data-root", root, "--port", "0")
	command.Dir = appDir
	command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}

	stdout, err := command.StdoutPipe()
	if err != nil {
		return err
	}
	stderrFile, err := os.CreateTemp(filepath.Join(root, "Temp"), "startup-*.log")
	if err != nil {
		return err
	}
	stderrPath := stderrFile.Name()
	defer stderrFile.Close()
	command.Stderr = stderrFile

	if err := command.Start(); err != nil {
		return fmt.Errorf("could not start the PDF engine: %w", err)
	}

	portChannel := make(chan string, 1)
	errorChannel := make(chan error, 1)
	go func() {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if strings.HasPrefix(line, "PORT=") {
				portChannel <- strings.TrimPrefix(line, "PORT=")
				return
			}
		}
		if err := scanner.Err(); err != nil {
			errorChannel <- err
		} else {
			errorChannel <- errors.New("the local PDF engine stopped before opening the application")
		}
	}()

	var port string
	select {
	case port = <-portChannel:
	case err := <-errorChannel:
		_ = command.Process.Kill()
		return fmt.Errorf("%w\n\nDiagnostic log: %s", err, stderrPath)
	case <-time.After(45 * time.Second):
		_ = command.Process.Kill()
		return fmt.Errorf("the local PDF engine did not start in time\n\nDiagnostic log: %s", stderrPath)
	}
	if strings.TrimSpace(port) == "" {
		_ = command.Process.Kill()
		return errors.New("the local PDF engine returned an invalid address")
	}

	url := "http://127.0.0.1:" + port + "/"
	if err := openAppWindow(url); err != nil {
		_ = command.Process.Kill()
		return err
	}

	waitErr := command.Wait()
	if waitErr != nil {
		// User shutdown can race with browser teardown. Only show an error when a useful log exists.
		if stat, statErr := os.Stat(stderrPath); statErr == nil && stat.Size() > 0 {
			return fmt.Errorf("the PDF engine closed unexpectedly\n\nDiagnostic log: %s", stderrPath)
		}
	}
	return nil
}

func openAppWindow(url string) error {
	edgeCandidates := []string{
		filepath.Join(os.Getenv("ProgramFiles(x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
		filepath.Join(os.Getenv("ProgramFiles"), "Microsoft", "Edge", "Application", "msedge.exe"),
		filepath.Join(os.Getenv("LOCALAPPDATA"), "Microsoft", "Edge", "Application", "msedge.exe"),
	}
	for _, edge := range edgeCandidates {
		if edge == "" {
			continue
		}
		if _, err := os.Stat(edge); err == nil {
			cmd := exec.Command(edge, "--app="+url, "--start-maximized", "--disable-features=msEdgeSidebarV2")
			cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
			if err := cmd.Start(); err == nil {
				return nil
			}
		}
	}
	cmd := exec.Command("rundll32.exe", "url.dll,FileProtocolHandler", url)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("could not open the application window: %w", err)
	}
	return nil
}
