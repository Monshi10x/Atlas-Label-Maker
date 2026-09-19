package main

import (
 "archive/zip"
 "bytes"
 "crypto/sha256"
 "fmt"
 "os"
 "path/filepath"
 "strings"
)

// Embedded Python ignores the script folder when its ._pth file enables
// isolation. Explicitly put this build's folder first, never the legacy App.
const pythonBootstrap = "import os,sys,runpy; p=sys.argv.pop(1); sys.path.insert(0,os.path.dirname(p)); sys.argv[0]=p; runpy.run_path(p,run_name='__main__')"

// Install into a new, immutable directory. Never remove/rename the legacy App
// directory or any completed build: another Python process may be using it.
func installApplication(root, version string, payload []byte) (string, error) {
 archive, err := zip.NewReader(bytes.NewReader(payload), int64(len(payload)))
 if err != nil { return "", fmt.Errorf("invalid application bundle: %w",err) }
 if !validVersion(version) { return "", fmt.Errorf("invalid application version: %q",version) }
 sum := sha256.Sum256(payload)
 identity := fmt.Sprintf("%x",sum)
 prefix := version+"-"+identity[:16]+"-"
 builds := filepath.Join(root,"AppVersions")
 if err := os.MkdirAll(builds,0755); err != nil { return "",fmt.Errorf("could not create application versions folder %s: %w",builds,err) }
 candidates, err := os.ReadDir(builds)
 if err != nil { return "",err }
 for _, entry := range candidates {
  if entry.IsDir() && strings.HasPrefix(entry.Name(),prefix) {
   path := filepath.Join(builds,entry.Name())
   if completeBuild(path,identity,archive.File) { return path,nil }
  }
 }
 // Unique paths also make simultaneous installers independent. The completion
 // marker is written last; interrupted installations are ignored on next start.
 target, err := os.MkdirTemp(builds,prefix)
 if err != nil { return "",fmt.Errorf("could not create a new application folder: %w",err) }
 success := false
 defer func(){ if !success { _ = os.RemoveAll(target) } }()
 if err := extractZipEntries(archive.File,target); err != nil { return "",fmt.Errorf("could not unpack new application files into %s: %w",target,err) }
 for _, name := range []string{"atlas_label_maker.py","app.version","static/index.html","vendor/pypdf/__init__.py"} {
  stat, err := os.Stat(filepath.Join(target,filepath.FromSlash(name)))
  if err != nil || !stat.Mode().IsRegular() { return "",fmt.Errorf("application bundle is missing %s",name) }
 }
 data,err := os.ReadFile(filepath.Join(target,"app.version"))
 if err != nil || strings.TrimSpace(string(data))!=version { return "",fmt.Errorf("bundle version does not match launcher version %s; rebuild with BUILD_WINDOWS.bat",version) }
 if err := os.WriteFile(filepath.Join(target,".bundle-complete"),[]byte(identity),0644); err != nil { return "",err }
 success=true
 return target,nil
}

func validVersion(version string) bool {
 if version=="" { return false }
 for _, c := range version { if !(c>='0' && c<='9') && c!='.' && c!='-' {return false} }
 return !strings.Contains(version,"..")
}

func completeBuild(path, identity string, files []*zip.File) bool {
 marker,err := os.ReadFile(filepath.Join(path,".bundle-complete"))
 if err!=nil || string(marker)!=identity {return false}
 for _, item := range files {
  if item.FileInfo().IsDir() {continue}
  stat,err := os.Stat(filepath.Join(path,filepath.FromSlash(item.Name)))
  if err!=nil || !stat.Mode().IsRegular() || uint64(stat.Size())!=item.UncompressedSize64 {return false}
 }
 return true
}
