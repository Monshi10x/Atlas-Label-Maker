ATLAS TOOLS LABEL SHEET BUILDER - VERSION 1.3.1

FIX FOR RENDERER LICENSE-DIRECTORY UNPACKING ERRORS
Update the features-6-10-26 checkout and rebuild with BUILD_WINDOWS.bat, then
launch the newly built EXE. The build now uses standard ZIP paths, and the
installer recognizes Windows directory records without creating them as files.
Close the previous app normally first. No AppData deletion is required; saved
templates, fonts, layouts and settings are retained.

FIX FOR "APP-UPDATE ... ACCESS IS DENIED"
This version no longer deletes or renames the installed App folder. Each
build installs into its own AppVersions subfolder, and completed builds
are reused. Saved templates, fonts, layouts and settings stay in place.

Extract this ZIP into a NEW folder, run BUILD_WINDOWS.bat, then launch the
NEW Atlas_Tools_Label_Sheet_Builder.exe beside this README. Close the old
app normally first. Do not reuse the old EXE. You do not need to delete
AppData or run as administrator. The Python shortcut below also works.

RUN
Extract the entire ZIP. With Python installed, double-click
RUN_WITH_PYTHON.bat. The app opens in your browser; keep the command window
open while using it. The shortcut installs the pinned PDF renderer into
app/vendor on first use (internet access required for dependency installation).

On Linux/macOS, use Python 3.12 or newer:
python -m pip install --no-deps --only-binary=:all: -r requirements.txt
python app/atlas_label_maker.py --data-root /path/to/atlas-data --port 8765

To build a Windows EXE, install Go and Python 3.12+ and run BUILD_WINDOWS.bat.
The build downloads the pinned Windows PDF renderer with pip. The EXE appears
beside this README. Its first launch downloads its private Python runtime.
No prebuilt EXE is included. All source and bundled dependencies are included.

WORKFLOW
Step 1 chooses a tool-label template from a folder of files. The included
55 x 15 mm Atlas template has Lorem Ipsum on both lines. Poppins Regular
is included and selected by default. No font upload is needed.

Step 2 contains a table: one row per uploaded PDF or newly added label.
Use ADD LABEL to add a row from the selected template, or upload several
PDFs at once. Each editable row has its own tool name, specification and
font choice. Edit directly in the table. There is no separate Save button:
preview, download and sheet generation use the current text in every row.
The original uploaded PDFs are never overwritten.

The selected row controls the preview, individual download and combined
output name. Clicking into another row's text also selects that row.
The name updates automatically as:
Tool Label - <Tool Name> <Specification>.pdf
For multiple labels, select the row whose name should identify the combined
PDF. Illegal filename characters are replaced with underscores.

Step 3 selects the A5 sheet layout and separate/mixed arrangement. Every
row is included in sheet generation, not just the selected row. Every
editable row is regenerated and validated before sheets are written. A row
with invalid/overlong text blocks output with its row number. A5 perimeter cut
contour adds a 1 pt spot-colour border; untick it to omit the sheet border.
Individual label cut contours remain included.

EXPORT ARTWORK
Sheet masters supply only page dimensions and placement positions. Their
sample artwork and old cut paths are removed before new labels are placed.
Rasterize artwork is enabled by default at 300 DPI. Choose a whole-number
resolution from 72 to 1200 DPI, or untick it to preserve vector artwork.
The setting applies to A5 exports and DOWNLOAD SELECTED PDF; previews remain
vector. Rasterize created text is enabled by default; untick it to preserve
edited tool names and specifications as vector text while rasterizing the
artwork. This text option is disabled when all artwork is kept vector.
Every exported PDF has two layers named artwork and cut. Artwork and created
text belong to artwork; all label cuts and the optional A5 border belong to
cut. CutContour paths remain vector spot colour in every mode. Use a PDF viewer
that supports layers to hide or show either layer. Raster images are losslessly compressed
and reused within a PDF. File size depends on the artwork and chosen DPI;
rasterization is not guaranteed to make every PDF smaller. The Windows build
bundles the renderer for its private Python runtime.

PDF PREVIEW
The actual PDF is rendered using bundled PDF.js. It scales up or down to
fill the viewer's width or height, keeping its aspect ratio and a 12 px
margin. Window resizing updates the fit. Drag the viewer corner to change
its height. Print/export dimensions are unaffected; print at actual size.

SUPPORTED EDITABLE PDF ARTWORK
The supplied 55 x 15 mm Atlas two-line format is recognized automatically,
including both lines' positions. Each uploaded label keeps its own artwork
when its text is regenerated. Other PDF layouts remain usable as original
PDFs, with read-only text columns marked 'PDF kept unchanged'. This avoids
placing replacement text over unrelated artwork. Size validation against
the selected A5 layout remains active for all rows.

TEMPLATE FILES
Click OPEN FOLDER in step 1, add matching Atlas-format label PDFs, then
LOAD / REFRESH. BROWSE or a pasted path selects another folder. Select a
template to replace the selected row's artwork and text, or use ADD LABEL
for another row. Rows based on files in another folder require selecting
that original folder before export; uploaded PDFs are independent of it.

Default folder:
%LOCALAPPDATA%\Atlas Tools Label Maker\LabelTemplates
It is seeded once from app/tool_label_templates and survives app updates.
The blank template is included at app/tool_label_templates/Atlas Tool Label.pdf.
Back up this folder separately from the A5 .atlaslabels layout backups.
The label table is session-only; exported PDFs remain in your output folder.

FONTS
Poppins-Regular.ttf is bundled, licensed under OFL 1.1, and embedded into
new PDFs. UPLOAD OTHER FONT accepts a static TTF; then choose Uploaded in
each row that should use it. Variable fonts and CFF/OTF are not supported.
An uploaded custom font persists between sessions. Replacing that font
changes subsequent rendering of rows set to Uploaded. Existing downloaded
PDFs are unaffected. Text starts at 5 pt and shrinks to fit down to 3 pt.

TESTS
python -m unittest discover -s tests -v
node tests/test_preview.mjs
cd launcher
go test install.go archive.go install_test.go

Native Windows EXE build, first-run runtime installation and folder dialogs
still need Windows verification. Python/PDF logic and browser workflows
were checked in Linux. See VALIDATION.md.
