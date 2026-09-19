package main

import (
 "archive/zip"
 "bytes"
 "os"
 "path/filepath"
 "sync"
 "testing"
)

func bundle(t *testing.T, version, content string) []byte {
 t.Helper()
 var b bytes.Buffer
 w := zip.NewWriter(&b)
 for _, item := range [][2]string{{"app.version",version},{"atlas_label_maker.py",content},{"static/index.html","html"},{"vendor/pypdf/__init__.py","pdf"}} {
  f, err := w.Create(item[0]); if err != nil { t.Fatal(err) }
  if _, err = f.Write([]byte(item[1])); err != nil { t.Fatal(err) }
 }
 if err := w.Close(); err != nil { t.Fatal(err) }; return b.Bytes()
}

func TestInstallPreservesLegacyAndUserData(t *testing.T) {
 root := t.TempDir()
 for _, dir := range []string{"App","Templates","LabelTemplates","Runtime","Backups"} {
  path := filepath.Join(root,dir)
  if err := os.MkdirAll(path,0755); err != nil { t.Fatal(err) }
  if err := os.WriteFile(filepath.Join(path,"keep"),[]byte("original"),0644); err != nil { t.Fatal(err) }
 }
 locked, err := os.Open(filepath.Join(root,"App","keep")); if err != nil { t.Fatal(err) }; defer locked.Close()
 payload := bundle(t,"1.3.1","first")
 path,err := installApplication(root,"1.3.1",payload); if err != nil { t.Fatal(err) }
 if filepath.Dir(path) != filepath.Join(root,"AppVersions") { t.Fatal(path) }
 again,err := installApplication(root,"1.3.1",payload); if err != nil || again != path { t.Fatalf("reuse: %q %v",again,err) }
 updated,err := installApplication(root,"1.3.1",bundle(t,"1.3.1","second")); if err != nil || updated == path { t.Fatalf("new payload: %q %v",updated,err) }
 for _, dir := range []string{"App","Templates","LabelTemplates","Runtime","Backups"} {
  data,err := os.ReadFile(filepath.Join(root,dir,"keep")); if err != nil || string(data)!="original" { t.Fatalf("changed %s",dir) }
 }
}

func TestInterruptedAndIncompleteBuildsAreSkipped(t *testing.T) {
 for _, missing := range []string{".bundle-complete","static/index.html"} {
  t.Run(missing,func(t *testing.T){
   root := t.TempDir(); payload := bundle(t,"1.3.1","first")
   old,err := installApplication(root,"1.3.1",payload); if err != nil { t.Fatal(err) }
   if err := os.Remove(filepath.Join(old,missing)); err != nil { t.Fatal(err) }
   next,err := installApplication(root,"1.3.1",payload); if err != nil || next==old { t.Fatalf("recovery: %q %v",next,err) }
   if _,err := os.Stat(old); err != nil { t.Fatal("previous folder removed",err) }
  })
 }
}

func TestFailedInstallPreservesGoodBuild(t *testing.T) {
 root:=t.TempDir(); good:=bundle(t,"1.3.1","first")
 path,err:=installApplication(root,"1.3.1",good); if err!=nil {t.Fatal(err)}
 for _, bad:=range [][]byte{[]byte("broken"),bundle(t,"wrong","bad")} {
  if _,err:=installApplication(root,"1.3.1",bad); err==nil {t.Fatal("accepted invalid bundle")}
 }
 again,err:=installApplication(root,"1.3.1",good); if err!=nil || again!=path {t.Fatalf("lost good build: %v",err)}
 entries,err:=os.ReadDir(filepath.Join(root,"AppVersions")); if err!=nil || len(entries)!=1 {t.Fatalf("failed install left files: %v",err)}
}

func TestConcurrentInstalls(t *testing.T) {
 root:=t.TempDir(); payload:=bundle(t,"1.3.1","first")
 var wg sync.WaitGroup
 for i:=0;i<8;i++ {wg.Add(1);go func(){defer wg.Done();path,err:=installApplication(root,"1.3.1",payload);if err!=nil {t.Error(err);return};data,err:=os.ReadFile(filepath.Join(path,"atlas_label_maker.py"));if err!=nil || string(data)!="first" {t.Errorf("incomplete build: %v",err)}}()}
 wg.Wait()
}

func TestArchiveTraversalRejected(t *testing.T) {
 var b bytes.Buffer; w:=zip.NewWriter(&b);f,err:=w.Create("../outside");if err!=nil {t.Fatal(err)};f.Write([]byte("bad"));w.Close()
 root:=t.TempDir()
 if err:=extractZipBytes(b.Bytes(),filepath.Join(root,"app"));err==nil {t.Fatal("accepted traversal")}
 if _,err:=os.Stat(filepath.Join(root,"outside"));!os.IsNotExist(err) {t.Fatal("wrote outside destination")}
}
