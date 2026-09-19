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
