# 1.3.1 launcher correction (supersedes older installation notes)

The old installer ignored errors deleting App, then renamed Temp/App-Update
onto that folder. Windows rejects this while a running Python process holds
files or its working directory open. The launcher now extracts directly into
AppVersions/<version>-<bundle SHA256 prefix>-<unique suffix>. No completed
build or legacy App folder is deleted or renamed. A full-hash completion
marker is written last; reuse additionally checks every bundled file's size.
Failed installs remove only their own newly created directory. Old builds
are retained deliberately to avoid deleting files used by another process.

The shared Python ._pth now contains only runtime paths. The launcher uses
pythonBootstrap to insert the chosen application directory and retain script
arguments. The application itself adds its vendored dependencies. Startup
logs are unique Temp/startup-*.log files. User-data paths are unchanged.

Run launcher tests with: go test install.go archive.go install_test.go
Windows build: BUILD_WINDOWS.bat. See VALIDATION.md for verification limits.

# Atlas Tools Label Sheet Builder — Project Handoff

## 1. Project identity

- **Application name:** Atlas Tools Label Sheet Builder
- **Current version:** 1.0.0
- **Target platform:** Windows 10/11, 64-bit
- **Primary owner:** Atlas Tools
- **Purpose:** Turn single tool-label PDFs into print-ready A5 label sheets using reusable templates, then add a mandatory 1 pt CutContour border to every generated A5 page.

This document is the technical source of truth for future changes. Preserve existing behaviour unless a requested change explicitly replaces it.

---

## 2. User workflow

### Template selection and management

The user selects an A5 template from a permanent template library.

The template manager supports:

- Add template
- Rename template
- Replace master PDF
- Edit accepted label dimensions
- Add, move, rotate, and delete label-placement slots
- Duplicate template
- Delete template
- Export the complete template library as one file
- Import/restore a complete template library

Template changes must persist after closing the application and after replacing the EXE with a newer build.

### Replacement-label upload

After selecting a template, the interface displays:

- Accepted replacement-label size in millimetres
- Number of available positions on the A5 template

The user uploads one or more single-page replacement PDFs. Uploaded PDF dimensions are validated against the selected template.

Current validation tolerance is **0.75 PDF points** per dimension.

### Sheet arrangements

#### One label design per A5 sheet

For every uploaded replacement PDF:

- Create one A5 sheet
- Fill every template slot with that same replacement label
- Preserve the master’s static artwork and all stored slot transforms

#### Combine into one page

- Use one A5 sheet
- Distribute the uploaded designs across all available slots using round-robin assignment
- The distribution is equal or as close to equal as possible
- Reject the operation when the number of uploaded designs exceeds the number of available slots

### Output choices

The user can select either or both:

- **Generate as a single PDF:** all generated A5 sheets are combined into one multipage PDF, with each A5 sheet as its own PDF page
- **Generate individual PDFs:** one single-page A5 PDF is written for every generated sheet

Combined output uses the user-entered output filename.

Individual output naming:

```text
<Original replacement label filename> A5 Sheet.pdf
```

For a mixed one-page sheet:

```text
<Combined output name> A5 Sheet.pdf
```

Existing files are not overwritten; a unique filename is generated when necessary.

---

## 3. Mandatory CutContour border

Every generated A5 page must receive the CutContour border, regardless of output mode.

Current implementation:

- Stroke width: **1 pt**
- Border location: inset **0.5 pt** from the MediaBox boundary so the full stroke remains on-page
- PDF colour space: `/Separation`
- Spot-colour name: `/CutContour`
- Internal resource name: `/ATCutContour`
- Alternate colour space: `/DeviceCMYK`
- Alternate CMYK values taken from the supplied `pueple.pdf`:
  - C: 11%
  - M: 100%
  - Y: 0%
  - K: 0%

Do not replace this with RGB or a normal process-colour stroke without explicit approval. The spot name and 1 pt width are production-critical.

Relevant source function:

```text
app/atlas_label_maker.py
add_cut_contour_border()
```

---

## 4. Supplied starter templates

### Compression 3.175x12 6D Ultraclean

- Accepted replacement size: **55 × 15 mm**
- Stored slot count: **31**
- Source master: `Compression 3.175x12 6D Ultraclean.pdf`
- Replacement test files:
  - `Compression 3.175x12 Ultraclean(1).pdf`
  - `Compression 3.175x12 Ultrapack(1).pdf`

### 3-4mm Collet

- Accepted replacement size: **35 × 35 mm**
- Stored slot count: **21**
- Source master: `3-4mm Collet.pdf`
- Replacement test files:
  - `Tool Label - Collet 5-6mm.pdf`
  - `Tool Label - Collet 7-8mm.pdf`

The two built-in templates are stored under:

```text
app/builtin_templates/
```

Each built-in template folder contains:

```text
master.pdf
template.json
```

Built-in templates are copied into permanent storage only on the first initialization of a user profile.

---

## 5. Permanent application data

Default data root:

```text
%LOCALAPPDATA%\Atlas Tools Label Maker
```

Created and checked automatically on launch:

```text
Atlas Tools Label Maker/
├── App/
├── Runtime/
├── Templates/
├── Backups/
├── Temp/
├── settings.json
└── .initialized
```

### Storage behaviour

- `App/` contains the unpacked embedded application files for the current app version
- `Runtime/` contains the private embedded Python runtime
- `Templates/` contains the permanent user template library
- `Backups/` contains automatic pre-import library backups
- `Temp/` contains temporary uploads and update staging
- `settings.json` remembers the last output folder and combined filename
- `.initialized` prevents starter templates from being reinstalled after the user deletes or modifies them

Updating or replacing the EXE must not delete `Templates/`, `Backups/`, or `settings.json`.

---

## 6. Template format

Each saved template has a unique 32-character hexadecimal ID and a folder:

```text
Templates/<template_id>/
├── master.pdf
└── template.json
```

Important `template.json` fields include:

```json
{
  "id": "32-character hex identifier",
  "name": "User-facing template name",
  "source_filename": "Original master filename",
  "page_width_pt": 0,
  "page_height_pt": 0,
  "accepted_width_pt": 0,
  "accepted_height_pt": 0,
  "accepted_width_mm": 0,
  "accepted_height_mm": 0,
  "slot_count": 0,
  "slots": [],
  "detection_method": "form-xobject | repeated-clips | edited",
  "is_a5": true,
  "created_at": "ISO-8601 UTC",
  "modified_at": "ISO-8601 UTC",
  "sort_order": 0
}
```

Each slot stores a PDF transformation matrix used by `merge_transformed_page()`.

Do not silently change the template JSON format. Introduce a format version and migration path if its structure changes.

---

## 7. Template import/export

Exported library extension:

```text
.atlaslabels
```

The file is a ZIP archive containing:

```text
manifest.json
templates/<template_id>/template.json
templates/<template_id>/master.pdf
```

Current manifest identifiers:

```json
{
  "format": "atlas-label-template-library",
  "format_version": 1
}
```

Import behaviour is a **complete restore**, not a merge:

1. Validate the package and every included master PDF
2. Write an automatic dated backup of the current library
3. Replace the current template library with the imported library
4. Preserve additions, deletions, renames, and slot edits exactly as they existed on the exporting computer

Automatic backup naming:

```text
Before-Import-YYYY-MM-DD-HHMMSS.atlaslabels
```

Relevant source functions:

```text
AppState.export_library()
AppState.import_library()
```

---

## 8. Application architecture

### Windows launcher

Language: **Go**

Source:

```text
launcher/main.go
```

Responsibilities:

- Find `%LOCALAPPDATA%`
- Create required folders
- Extract/update the embedded application bundle
- Download and verify the private Python runtime on first launch
- Configure Python’s `._pth` file
- Start the local Python application
- Open the interface in a Microsoft Edge app window, with browser fallback
- Display native Windows error dialogs when startup fails

Current private runtime:

- Python 3.12.10 embedded, AMD64
- Downloaded from python.org on first launch
- Archive integrity checked using the checksum embedded in `launcher/main.go`

The first launch requires internet access. Later launches use the saved runtime.

### Local application and PDF engine

Language: **Python**

Main source:

```text
app/atlas_label_maker.py
```

Core dependency:

```text
pypdf
```

The required `pypdf` package is vendored under:

```text
app/vendor/pypdf/
```

The Python process runs a local `ThreadingHTTPServer` and serves both the user interface and JSON API.

### User interface

Files:

```text
app/static/index.html
app/static/styles.css
app/static/app.js
```

Visual direction:

- Based on the supplied Atlas Tools website screenshot
- Matte black background
- Atlas gold primary accents
- White condensed uppercase headings
- Dark-grey cards and thin borders
- Subtle angular/diagonal linework
- Minimal, uncluttered, businesslike layout
- Clear step-by-step workflow
- Gold-filled primary controls and outlined secondary controls

Preserve this appearance unless a redesign is explicitly requested.

---

## 9. HTTP API summary

Current API routes include:

```text
GET    /api/status
GET    /api/templates
GET    /api/templates/<id>/master.pdf
GET    /api/ping

POST   /api/templates/upload
POST   /api/templates/<id>/replace-master
POST   /api/templates/<id>/duplicate
POST   /api/labels/upload
POST   /api/templates/export
POST   /api/templates/import
POST   /api/select-output-folder
POST   /api/generate
POST   /api/open-folder
POST   /api/shutdown

PUT    /api/templates/<id>

DELETE /api/templates/<id>
DELETE /api/labels/<token>
```

Uploaded replacement-label PDFs are temporary and are not part of the permanent template library.

---

## 10. PDF generation behaviour

Relevant function:

```text
AppState.generate()
```

Process:

1. Load the selected template and stored slots
2. Validate every replacement-label PDF against the accepted dimensions
3. Load page 1 of each replacement PDF
4. Add the saved master page to a new writer
5. Overlay each assigned replacement PDF with its stored slot matrix
6. Add the CutContour border
7. Write combined and/or individual outputs

Only the first page of each replacement-label PDF is used.

The master page is retained so any static artwork, registration marks, or backgrounds remain present.

Relevant functions:

```text
validate_label_sizes()
build_sheet_page()
add_cut_contour_border()
```

---

## 11. Automatic template detection

When adding or replacing a master PDF, the application analyses its first page and attempts to identify repeated label placements.

Current detection functions:

```text
analyze_template()
detect_form_xobject_slots()
detect_repeated_clip_slots()
```

Possible detection methods recorded in template metadata:

```text
form-xobject
repeated-clips
edited
```

The template editor allows manual correction after detection.

Future changes must be tested against both starter templates because they exercise different layout structures.

---

## 12. Build instructions

### Requirements

- Windows 10/11
- Go installed and available through `PATH`
- PowerShell `Compress-Archive`

### Build

Run:

```text
BUILD_WINDOWS.bat
```

The build script:

1. Deletes the previous `launcher/app_bundle.zip`
2. Compresses `app/*` into `launcher/app_bundle.zip`
3. Sets:
   - `GOOS=windows`
   - `GOARCH=amd64`
   - `CGO_ENABLED=0`
4. Builds a GUI-subsystem executable:

```text
Atlas_Tools_Label_Sheet_Builder.exe
```

Important: update both Python and Go version constants when releasing a new version:

```text
app/atlas_label_maker.py      APP_VERSION
launcher/main.go              appVersion
app/app.version
```

The launcher replaces the unpacked `App/` folder when its stored app version differs from the EXE version, while leaving permanent templates and settings intact.

---

## 13. Required regression tests

Before delivering any updated build, test all of the following.

### Startup and persistence

- First launch creates every required folder
- Runtime installation succeeds
- Later launch works without downloading again
- Added template remains after closing and reopening
- Renamed template remains renamed
- Edited slots remain edited
- Deleted template does not reappear
- Replacing the EXE does not erase templates

### Template library

- Add each starter-template type
- Duplicate template
- Replace master
- Modify accepted dimensions
- Add, move, rotate, and delete slots
- Export library
- Delete/alter templates
- Import library and confirm exact restoration
- Confirm automatic pre-import backup is created

### Label validation

- Correct-size compression labels are accepted
- Correct-size collet labels are accepted
- Incorrect dimensions produce a clear error
- Invalid/corrupt PDFs produce a clear error
- Multiple-page label PDFs use page 1 only

### Output arrangements

- One uploaded label → one filled A5 sheet
- Multiple uploaded labels → separate filled A5 sheets
- Mixed one-page layout distributes labels evenly or nearly evenly
- More unique labels than slots is rejected
- Combined multipage output is valid
- Individual output is valid
- Both options selected together are valid
- Existing filenames are not overwritten

### CutContour

On every generated page verify:

- `/Separation` colour space exists
- Spot name is `/CutContour`
- Alternate CMYK is 0.11 / 1 / 0 / 0
- Stroke width is 1 pt
- Border is visible and remains within the page boundary
- Border is present in individual, combined, and mixed outputs

### Visual checks

Render generated PDFs and compare:

- Slot positions
- Scaling
- Rotation
- No unexpected cropping
- No artwork rasterisation introduced by the application
- A5 MediaBox remains correct
- Static master artwork remains intact

---

## 14. Known limitations and cautions

- The application currently uses only page 1 of a master or replacement PDF
- First launch depends on the configured Python download URL remaining available
- The Windows launcher was originally cross-compiled in Linux; Windows operation should continue to be tested directly for future releases
- Template auto-detection may require manual slot correction for unusual PDF structures
- Template import replaces the entire library rather than merging it
- The program is not an Illustrator editor; it overlays replacement PDFs into stored positions
- `pypdf` is vendored, so dependency upgrades require deliberate testing
- The current CutContour alternate values are hard-coded from the supplied colour PDF

---

## 15. Files that should accompany future change requests

Always retain and supply:

1. Latest source ZIP
2. Latest working EXE
3. This `PROJECT_HANDOFF.md`
4. Latest `CHANGELOG.md`
5. Exported `.atlaslabels` template-library backup
6. The affected template master PDFs
7. Representative original-size replacement-label PDFs
8. A clear description of the requested change and expected output

Recommended future request wording:

> Study PROJECT_HANDOFF.md and the supplied source before editing. Preserve all existing behaviour unless the requested change explicitly replaces it. Build and regression-test the change against both starter template types.

---

## 16. Original reference assets

Reference files used for version 1.0.0:

```text
pueple(1).pdf
Compression 3.175x12 6D Ultraclean.pdf
Compression 3.175x12 Ultraclean(1).pdf
Compression 3.175x12 Ultrapack(1).pdf
3-4mm Collet.pdf
Tool Label - Collet 5-6mm.pdf
Tool Label - Collet 7-8mm.pdf
image(13).png
```

These assets are not all necessarily included inside the source archive. Keep a separate project backup of them.


## 17. Version 1.1.0 - editable label designer

Current release: 1.1.0 (supersedes version 1.0.0 references above).
`app/label_designer.py` retains the supplied compression.pdf artwork and
removes its text-show operators before adding two vector text lines.
FontTools (pure Python, vendored) reads static TTF fonts; CIDFontType2 embeds
the full font with per-character widths, CIDToGIDMap and ToUnicode.
DejaVu Sans is the bundled fallback. Poppins is not bundled; upload a static
Poppins-Regular.ttf for the original typography. No extra runtime install.

Endpoints: GET /api/designer; POST /api/designer/font (binary TTF),
/api/designer/preview (JSON -> PDF), /api/designer/add (JSON -> upload record).
JSON fields: title, specification, use_custom_font. Draft and font persist
atomically in data-root/LabelDesigner, separate from template library backups.
Queued design edit metadata lives in the current browser session only.
A font change does not change PDFs already in the queue until regenerated.
New files: label_designer.py, label_assets/*, vendor/fontTools/*,
RUN_WITH_PYTHON.bat, tests/test_designer.py. All release version markers updated.
BUILD_WINDOWS.bat now emits the EXE in the source root, not its parent.

Run tests: python -m unittest discover -s tests -v
Actual Windows UI/launcher and native dialogs have not been verified here.
The source contains no compiled EXE. All previous template formats unchanged.


## 18. Release 1.3.0 - editable table and fitted preview

This section supersedes earlier designer workflow notes.
The current release marker is 1.3.0 in Python, Go and app.version.
Step 1 chooses a tool-label PDF from a folder. Step 2 stores an array of
rows in state.uploads; each has rowId, source_token or tool_template_id,
template_folder, title, specification, editable and use_custom_font.
Step 3 chooses A5 layout/output. Existing sheet-template APIs are retained.

Uploaded files are inspected for the 55 x 15 mm two-line Atlas artwork,
including text baselines. Supported files expose extracted title/specification;
other PDFs remain unmodified and read-only in the text columns. Never mark
unrecognized artwork editable and silently overwrite its text. Source PDFs
remain immutable in session uploads. create_label accepts source_path and
removes page text-show operators before drawing the replacement text.

/api/generate accepts label_rows. AppState.generate_rows regenerates all
editable rows, validates before final sheet output, and cleans generated
temporary uploads in finally. Existing label_tokens requests remain supported.
/api/designer/preview accepts the row payload, or passes through original
PDF bytes for read-only rows. A selected row's fields drive the combined
filename. Preview selection does not filter which rows are exported.

GET /api/tool-templates returns folder/templates/errors.
POST /api/tool-templates/folder sets or browses for the template folder.
LabelTemplates is seeded once with the blank Lorem Ipsum label. Current
support is matching Atlas two-line PDFs, not arbitrary field layouts.
Folder-backed rows carry the folder identity so a same-named file from a
new folder cannot be substituted silently. Uploaded source tokens are
independent of template folder changes. All table state remains session-only.

static/label-preview.mjs uses bundled legacy PDF.js. fitScale is the lesser
of available width/page width and height/page height after 12 px margins.
ResizeObserver updates fit. Rendering occurs offscreen and the completed
frame is copied to the visible canvas. A previous frame scales immediately
while rerendering, preventing a blank white frame during resize. PDF size
is never altered by preview scaling. .mjs and .wasm MIME types are provided.

Poppins is the bundled default; font name/ToUnicode/widths and the full TTF
are embedded. FontTools and PDF.js are vendored with licenses. No runtime
package install or CDN is needed. RUN_WITH_PYTHON.bat uses --open-browser.
