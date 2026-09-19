# 1.3.1

- Fixed startup failure when Windows denies replacing the installed App folder.
- Install each distinct bundle in a separate, uniquely named AppVersions folder.
- Reuse only completed installations; ignore interrupted/incomplete builds.
- Keep legacy application files and all user data in place.
- Load Python modules from the selected build, and use separate startup logs.
- Added installer regression tests for preservation, reuse, recovery and concurrency.

# 1.3.0

- Bundled Poppins Regular and Lorem Ipsum label template.
- Added one independently editable table row per uploaded/new label.
- Preview/download/export use current row text; originals remain intact.
- Combined PDF name follows the selected row: Tool Label - name specification.
- Added fitted PDF.js preview with resize support and 12 px margins.
- Step 1 selects tool-label artwork from a folder; A5 layout moved to step 3.
- Python launcher now opens the browser automatically.

# 1.1.0

- Added editable tool name/specification for supplied 55 x 15 mm artwork.
- Actual PDF preview, standalone download, add/edit labels in sheet queue.
- Static TTF upload, embedding, persistent font and last-used text.
- Bundled DejaVu Sans fallback; auto-fit with 3 pt readability guard.
- Retained existing template management, PDF uploads and CutContour outputs.
- Added regression tests and Python launch shortcut; fixed build output path.

# Changelog

All notable changes to Atlas Tools Label Sheet Builder should be recorded here.

## 1.0.0 — 2026-07-25

### Added

- Windows 10/11 64-bit standalone launcher
- Automatic `%LOCALAPPDATA%\Atlas Tools Label Maker` folder creation
- Private Python 3.12 embedded-runtime installation on first launch
- Permanent user template library
- Built-in 55 × 15 mm compression template
- Built-in 35 × 35 mm collet template
- Add, rename, replace, duplicate, edit, and delete template functions
- Visual placement-slot editing
- Complete template-library export/import through `.atlaslabels`
- Automatic backup before library import
- Replacement-label PDF size validation
- One-design-per-A5-sheet generation
- Mixed-design single-A5-sheet generation
- Combined multipage PDF output
- Individual A5 PDF output
- Automatic unique output filenames
- Mandatory 1 pt `/CutContour` spot-colour border on every generated A5 page
- Atlas Tools website-inspired interface
- Local browser-based interface backed by a Python HTTP server

### Technical notes

- PDF processing uses vendored `pypdf`
- CutContour alternate CMYK values are 11 / 100 / 0 / 0
- Template library format version is 1
- Source handoff documentation added after the initial package release
