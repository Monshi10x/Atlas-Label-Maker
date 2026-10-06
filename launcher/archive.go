package main

import (
	"archive/zip"
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

func extractZipFile(zipPath, destination string) error {
	archive, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer archive.Close()
	return extractZipEntries(archive.File, destination)
}

func extractZipBytes(data []byte, destination string) error {
	archive, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return err
	}
	return extractZipEntries(archive.File, destination)
}

func extractZipEntries(files []*zip.File, destination string) error {
	cleanRoot, err := filepath.Abs(destination)
	if err != nil {
		return err
	}
	for _, item := range files {
		cleanName, err := archiveEntryName(item.Name)
		if err != nil {
			return err
		}
		target := filepath.Join(cleanRoot, cleanName)
		if !strings.HasPrefix(strings.ToLower(target), strings.ToLower(cleanRoot+string(os.PathSeparator))) && target != cleanRoot {
			return fmt.Errorf("unsafe archive entry: %s", item.Name)
		}
		if archiveEntryIsDir(item) {
			if err := os.MkdirAll(target, 0755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
			return err
		}
		source, err := item.Open()
		if err != nil {
			return err
		}
		output, err := os.OpenFile(target, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, item.Mode())
		if err != nil {
			source.Close()
			return err
		}
		_, copyErr := io.Copy(output, source)
		closeOutErr := output.Close()
		closeSourceErr := source.Close()
		if copyErr != nil {
			return copyErr
		}
		if closeOutErr != nil {
			return closeOutErr
		}
		if closeSourceErr != nil {
			return closeSourceErr
		}
	}
	return nil
}

// PowerShell archives can use backslashes and omit directory mode bits.
// Normalize names before either extracting or verifying an installed build.
func archiveEntryName(name string) (string, error) {
	normalized := strings.ReplaceAll(name, "\\", "/")
	cleanName := filepath.Clean(filepath.FromSlash(normalized))
	if cleanName == "." || cleanName == ".." || strings.HasPrefix(normalized, "/") ||
		strings.Contains(normalized, ":") || strings.ContainsRune(normalized, '\x00') ||
		filepath.IsAbs(cleanName) || strings.HasPrefix(cleanName, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("unsafe archive entry: %s", name)
	}
	return cleanName, nil
}

func archiveEntryIsDir(item *zip.File) bool {
	return item.FileInfo().IsDir() || strings.HasSuffix(item.Name, "/") || strings.HasSuffix(item.Name, "\\")
}
