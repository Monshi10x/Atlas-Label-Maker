# Windows renderer unpacking fix validation

- All 7 Go installer tests passed, including the renderer's nested license
  tree with Windows separators and directory records lacking mode bits, reuse
  of that installation, and 6 mixed/Windows path traversal rejection cases.
- Python bundle regression passed: standard forward-slash file names, renderer
  DLL and license preservation, cache exclusion and repeatable archive refresh.
- Packaged the real application and Windows renderer with the new builder.
  Installed and compared all 674 archive files byte for byte, then verified
  completed-build reuse using the actual launcher installer on Linux.
- Current launcher and bundle cross-compiled to a Windows AMD64 GUI EXE.

LIMIT: Native Windows launch was not available in this cloud environment.

# Version 1.3.1 validation

- Python bootstrap checked with isolated Python (-I -S), an application path
  containing spaces, sibling imports and argument preservation: passed.
- Actual application entry point loads vendored dependencies through the new
  bootstrap: passed. Local HTTP startup and page response: passed.
- Source reviewed: no deletion/rename of legacy App or completed builds;
  unique install folders and startup logs; completion marker written last.
- Added Go regression tests: legacy/user-data preservation, identical build
  reuse, changed bundle isolation, missing marker/file recovery, failed
  install cleanup, simultaneous installation and ZIP traversal rejection.
- BUILD_WINDOWS.bat now runs those tests before building the EXE.

LIMITS: Go is unavailable in this environment and toolchain download was
blocked. The Go regression tests and Windows compilation have NOT been run
here. No prebuilt EXE is included. Native Windows startup, Windows file-lock
behavior and runtime installation must be verified after building locally.

# Version 1.3.0 validation

- Python tests: original sheet workflows, text validation, exact label size,
  uploaded-label detection, independent row regeneration, separate/mixed
  output, source preservation, temporary-file cleanup and CutContour.
- Bundled Poppins TTF embedding and Lorem Ipsum template text verified.
- Browser: uploaded two PDFs, edited both rows independently, checked
  automatic filename changes, selected/previewed a row, resized the viewer
  against width/height limits, downloaded the selected label and generated
  a two-page combined PDF directly from the edited table.
- Reopened that browser-generated PDF and verified the correct edited text
  appeared on each page, without the other row's edited name.
- Preview screenshot and rendered label PDF visually inspected.
- Numeric fitScale tests and JavaScript syntax checks passed.
- No system-installed Python packages are required (dependencies vendored).

Windows EXE build, runtime download and native folder picker were not run
in this Linux environment. Full Windows build instructions are included.
# features-6-10-26 validation

- All 10 Python regression tests passed, including clean exports for both
  starter layouts, combined/individual outputs, mixed labels, source
  preservation, vector opt-out, DPI validation and default 300 DPI rasterizing.
- Actual CutContour paint counts checked: one per placed label plus the A5
  border, with no master artwork or old master cut paths in either mode.
- 150/300/600 DPI raster dimensions checked. A synthetic coloured label and a
  nested form verify that cut-line pixels are absent from the raster image,
  while the spot-colour cutter remains in vector content.
- Browser checks passed in Chromium: defaults, checkbox/DPI controls, row edits,
  raster/vector sheet generation, selected-label raster download, invalid DPI
  rejection and restoration of saved export settings. Generated PDFs were
  inspected for actual artwork, edited text, image reuse and vector cuts;
  raster and vector sheets were rendered and visually inspected.
- JavaScript syntax and existing preview-fit checks passed.
- All 5 Go launcher regression tests (including 2 subtests) passed. A current
  source bundle including the Windows renderer DLL and its license notices
  cross-compiled to a Windows AMD64 GUI EXE in an external staging directory.

LIMITS: Native Windows startup/runtime download and folder dialogs were not
executed. Raster file size depends on artwork and resolution.
