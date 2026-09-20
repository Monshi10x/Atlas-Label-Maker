from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

APP_VERSION = "1.3.1"
APP_NAME = "Atlas Tools Label Sheet Builder"
MM_TO_PT = 72.0 / 25.4
PT_TO_MM = 25.4 / 72.0
A5_WIDTH_PT = 148 * MM_TO_PT
A5_HEIGHT_PT = 210 * MM_TO_PT
UPLOAD_LIMIT = 600 * 1024 * 1024

APP_DIR = Path(__file__).resolve().parent
VENDOR_DIR = APP_DIR / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)


from label_designer import create_label, read_font


class AppError(Exception):
    pass


@dataclass
class AppPaths:
    root: Path
    templates: Path
    backups: Path
    temp: Path
    settings: Path
    initialized: Path

    @classmethod
    def create(cls, root: Path) -> "AppPaths":
        paths = cls(
            root=root,
            templates=root / "Templates",
            backups=root / "Backups",
            temp=root / "Temp",
            settings=root / "settings.json",
            initialized=root / ".initialized",
        )
        for p in (paths.root, paths.templates, paths.backups, paths.temp):
            p.mkdir(parents=True, exist_ok=True)
        return paths


class AppState:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.lock = threading.RLock()
        self.last_heartbeat = time.time()
        self.uploads: dict[str, dict[str, Any]] = {}
        self.shutdown_requested = threading.Event()
        self.settings = self._load_settings()
        self._install_builtin_templates_once()
        self._cleanup_temp()

    def _load_settings(self) -> dict[str, Any]:
        default = {
            "version": 1,
            "last_output_folder": str(Path.home() / "Documents"),
            "combined_name": "Atlas Tool Labels",
        }
        try:
            if self.paths.settings.exists():
                loaded = json.loads(self.paths.settings.read_text(encoding="utf-8"))
                default.update(loaded)
        except Exception:
            pass
        self._save_settings(default)
        return default

    def _save_settings(self, settings: dict[str, Any] | None = None) -> None:
        if settings is not None:
            self.settings = settings
        tmp = self.paths.settings.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        tmp.replace(self.paths.settings)

    def _install_builtin_templates_once(self) -> None:
        if self.paths.initialized.exists():
            return
        builtin_root = APP_DIR / "builtin_templates"
        if builtin_root.exists():
            for source in builtin_root.iterdir():
                if not source.is_dir():
                    continue
                target = self.paths.templates / source.name
                if not target.exists():
                    shutil.copytree(source, target)
        self.paths.initialized.write_text(
            json.dumps({"version": APP_VERSION, "created": utc_now()}), encoding="utf-8"
        )

    def _cleanup_temp(self) -> None:
        cutoff = time.time() - 24 * 3600
        for child in self.paths.temp.glob("*"):
            try:
                if child.stat().st_mtime < cutoff:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
            except Exception:
                pass

    def list_templates(self) -> list[dict[str, Any]]:
        with self.lock:
            templates: list[dict[str, Any]] = []
            for folder in self.paths.templates.iterdir():
                if not folder.is_dir():
                    continue
                meta_path = folder / "template.json"
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["available"] = (folder / "master.pdf").exists()
                    templates.append(meta)
                except Exception:
                    continue
            templates.sort(key=lambda x: (x.get("sort_order", 9999), x.get("name", "").lower()))
            return templates

    def get_template(self, template_id: str) -> tuple[dict[str, Any], Path]:
        safe_id(template_id)
        folder = self.paths.templates / template_id
        meta_path = folder / "template.json"
        if not meta_path.exists():
            raise AppError("Template not found.")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta, folder

    def save_template(self, meta: dict[str, Any], folder: Path) -> None:
        meta["modified_at"] = utc_now()
        tmp = folder / "template.tmp"
        tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        tmp.replace(folder / "template.json")

    def create_template(self, name: str, pdf_bytes: bytes, filename: str) -> dict[str, Any]:
        if not pdf_bytes.startswith(b"%PDF"):
            raise AppError("The selected file is not a valid PDF.")
        template_id = uuid.uuid4().hex
        folder = self.paths.templates / template_id
        folder.mkdir(parents=True, exist_ok=False)
        master = folder / "master.pdf"
        master.write_bytes(pdf_bytes)
        try:
            analysis = analyze_template(master)
            now = utc_now()
            meta = {
                "id": template_id,
                "name": clean_display_name(name or Path(filename).stem),
                "source_filename": filename,
                "created_at": now,
                "modified_at": now,
                "page_width_pt": analysis["page_width_pt"],
                "page_height_pt": analysis["page_height_pt"],
                "accepted_width_pt": analysis["accepted_width_pt"],
                "accepted_height_pt": analysis["accepted_height_pt"],
                "accepted_width_mm": analysis["accepted_width_pt"] * PT_TO_MM,
                "accepted_height_mm": analysis["accepted_height_pt"] * PT_TO_MM,
                "slot_count": len(analysis["slots"]),
                "slots": analysis["slots"],
                "detection_method": analysis["detection_method"],
                "is_a5": analysis["is_a5"],
                "sort_order": int(time.time()),
            }
            self.save_template(meta, folder)
            return meta
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def update_template(self, template_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            meta, folder = self.get_template(template_id)
            if "name" in payload:
                meta["name"] = clean_display_name(str(payload["name"]))
            if "accepted_width_mm" in payload:
                val = float(payload["accepted_width_mm"])
                if not 1 <= val <= 300:
                    raise AppError("Label width must be between 1 mm and 300 mm.")
                meta["accepted_width_mm"] = val
                meta["accepted_width_pt"] = val * MM_TO_PT
            if "accepted_height_mm" in payload:
                val = float(payload["accepted_height_mm"])
                if not 1 <= val <= 300:
                    raise AppError("Label height must be between 1 mm and 300 mm.")
                meta["accepted_height_mm"] = val
                meta["accepted_height_pt"] = val * MM_TO_PT
            if "slots" in payload:
                slots = validate_slots(payload["slots"], meta)
                meta["slots"] = slots
                meta["slot_count"] = len(slots)
                meta["detection_method"] = "edited"
            self.save_template(meta, folder)
            return meta

    def replace_template_master(self, template_id: str, pdf_bytes: bytes, filename: str) -> dict[str, Any]:
        if not pdf_bytes.startswith(b"%PDF"):
            raise AppError("The selected file is not a valid PDF.")
        with self.lock:
            meta, folder = self.get_template(template_id)
            new_master = folder / "master-new.pdf"
            new_master.write_bytes(pdf_bytes)
            try:
                analysis = analyze_template(new_master)
                (folder / "master.pdf").unlink(missing_ok=True)
                new_master.replace(folder / "master.pdf")
                meta.update({
                    "source_filename": filename,
                    "page_width_pt": analysis["page_width_pt"],
                    "page_height_pt": analysis["page_height_pt"],
                    "accepted_width_pt": analysis["accepted_width_pt"],
                    "accepted_height_pt": analysis["accepted_height_pt"],
                    "accepted_width_mm": analysis["accepted_width_pt"] * PT_TO_MM,
                    "accepted_height_mm": analysis["accepted_height_pt"] * PT_TO_MM,
                    "slots": analysis["slots"],
                    "slot_count": len(analysis["slots"]),
                    "detection_method": analysis["detection_method"],
                    "is_a5": analysis["is_a5"],
                })
                self.save_template(meta, folder)
                return meta
            except Exception:
                new_master.unlink(missing_ok=True)
                raise

    def delete_template(self, template_id: str) -> None:
        safe_id(template_id)
        folder = self.paths.templates / template_id
        if not folder.exists():
            raise AppError("Template not found.")
        shutil.rmtree(folder)

    def duplicate_template(self, template_id: str) -> dict[str, Any]:
        with self.lock:
            meta, folder = self.get_template(template_id)
            new_id = uuid.uuid4().hex
            new_folder = self.paths.templates / new_id
            shutil.copytree(folder, new_folder)
            new_meta = json.loads((new_folder / "template.json").read_text(encoding="utf-8"))
            new_meta["id"] = new_id
            new_meta["name"] = f"{new_meta['name']} Copy"
            new_meta["created_at"] = utc_now()
            new_meta["sort_order"] = int(time.time())
            self.save_template(new_meta, new_folder)
            return new_meta

    def label_text(self, page):
        """Recognize this two-field artwork before making its text editable."""
        if page.rotation or abs(float(page.mediabox.width)-55*MM_TO_PT)>.75 or abs(float(page.mediabox.height)-15*MM_TO_PT)>.75:
            return None
        found=[]
        def visit(text, cm, tm, font, size):
            if text.strip():
                found.append((text.strip(), tm[4]*cm[0]+tm[5]*cm[2]+cm[4], tm[4]*cm[1]+tm[5]*cm[3]+cm[5],cm,tm))
        page.extract_text(visitor_text=visit)
        if len(found)!=2: return None
        for row,y in zip(found,(25.542,13.3013)):
            if abs(row[1]-84.1699)>.5 or abs(row[2]-y)>.5 or any(abs(v)>.001 for v in (row[3][1],row[3][2],row[4][1],row[4][2])):
                return None
        # Do not replace text that lives inside a nested form.
        def nested_text(resources, seen):
            for ref in resources.get('/XObject',{}).values():
                obj=ref.get_object()
                if id(obj) in seen: continue
                seen.add(id(obj))
                if obj.get('/Subtype')=='/Form':
                    if any(op in (b'Tj',b'TJ',b"'",b'"') for _,op in ContentStream(obj,page.pdf).operations):return True
                    if nested_text(obj.get('/Resources',{}),seen):return True
            return False
        if nested_text(page.get('/Resources',{}),set()):return None
        return {"title":found[0][0],"specification":found[1][0]}

    def tool_folder(self):
        folder=self.paths.root / "LabelTemplates"
        folder.mkdir(exist_ok=True)
        if not (folder / '.initialized').exists():
            for source in (APP_DIR/'tool_label_templates').glob('*.pdf'):
                if not (folder/source.name).exists():shutil.copy2(source,folder/source.name)
            (folder/'.initialized').write_text('1')
        return Path(self.settings.get('tool_template_folder') or folder)

    def tool_templates(self):
        folder=self.tool_folder();items=[];errors=[]
        if not folder.is_dir():raise AppError('The label-template folder is unavailable. Choose another folder.')
        for path in sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.pdf'),key=lambda p:p.name.lower()):
            try:
                reader=PdfReader(path)
                text=self.label_text(reader.pages[0]) if len(reader.pages)==1 else None
                if not text:raise AppError('Use a single 55 x 15 mm Atlas two-line label with live text in the standard positions.')
                items.append({'id':path.name,'name':path.stem,**text,'width_pt':55*MM_TO_PT,'height_pt':15*MM_TO_PT})
            except Exception as exc:errors.append(path.name+': '+str(exc))
        return {'templates':items,'errors':errors,'folder':str(folder)}

    def source_for_row(self, payload):
        if payload.get('source_token'):
            info=self.get_upload(str(payload['source_token']))
            if not info.get('editable'):raise AppError('This PDF is kept as supplied; editable Atlas text was not detected.')
            return Path(info['path'])
        folder=self.tool_folder()
        if payload.get('template_folder') and Path(payload['template_folder']).resolve()!=folder.resolve():
            raise AppError('A row uses another template folder. Select its original folder or remove that row.')
        name=str(payload.get('tool_template_id','Atlas Tool Label.pdf'))
        if Path(name).name!=name or '/' in name or "\\" in name:raise AppError('Invalid label template.')
        path=folder/name
        if not path.is_file():raise AppError('Label template is missing. Refresh the template folder.')
        reader=PdfReader(path)
        if len(reader.pages)!=1 or not self.label_text(reader.pages[0]):raise AppError('This template is not an editable Atlas label.')
        return path

    def generate_rows(self,payload):
        rows=payload.get('label_rows')
        if rows is None:return self.generate(payload)
        if not isinstance(rows,list) or not 1<=len(rows)<=200:raise AppError('Add between 1 and 200 labels.')
        tokens=[];temporary=[]
        try:
            # Validate/regenerate all edited rows before writing any output sheets.
            for i,row in enumerate(rows):
                try:
                    if row.get('editable'):
                        data,_=self.designer_pdf(row)
                        name='Tool Label - '+str(row.get('title','')).strip()+' '+str(row.get('specification','')).strip()+'.pdf'
                        info=self.store_label_upload(name,data);tokens.append(info['token']);temporary.append(info['token'])
                    else:
                        token=str(row.get('source_token',''));self.get_upload(token);tokens.append(token)
                except Exception as exc:raise AppError(f'Label row {i+1}: {exc}') from exc
            return self.generate({**payload,'label_tokens':tokens})
        finally:
            for token in temporary:self.remove_upload(token)

    def designer_info(self):
        folder = self.paths.root / "LabelDesigner"
        try:
            saved = json.loads((folder / "draft.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {"title": "Lorem Ipsum", "specification": "Lorem Ipsum"}
        return {"draft": saved, "custom_font": (folder / "font.ttf").exists()}

    def designer_font(self, data):
        try:
            read_font(data)
        except Exception as exc:
            raise AppError(str(exc)) from exc
        with self.lock:
            folder = self.paths.root / "LabelDesigner"
            folder.mkdir(exist_ok=True)
            temp = folder / "font.tmp"
            temp.write_bytes(data)
            temp.replace(folder / "font.ttf")

    def designer_pdf(self, payload):
        with self.lock:
            font = self.paths.root / "LabelDesigner" / "font.ttf"
            data = font.read_bytes() if payload.get("use_custom_font", True) and font.exists() else None
        try:
            return create_label(payload, data, self.source_for_row(payload))
        except Exception as exc:
            raise AppError(str(exc)) from exc

    def designer_add(self, payload):
        data, sizes = self.designer_pdf(payload)
        name = sanitize_filename(str(payload.get("title", "Label")) + " " + str(payload.get("specification", "")), default="Label") + ".pdf"
        with self.lock:
            info = self.store_label_upload(name, data)
            folder = self.paths.root / "LabelDesigner"
            folder.mkdir(exist_ok=True)
            temp = folder / "draft.tmp"
            temp.write_text(json.dumps(payload), encoding="utf-8")
            temp.replace(folder / "draft.json")
        return {"upload": info, "font_sizes": sizes}

    def store_label_upload(self, filename: str, data: bytes) -> dict[str, Any]:
        if not data.startswith(b"%PDF"):
            raise AppError(f"{filename} is not a valid PDF.")
        token = uuid.uuid4().hex
        safe_name = sanitize_filename(filename, default="label.pdf")
        path = self.paths.temp / f"{token}-{safe_name}"
        path.write_bytes(data)
        try:
            reader = PdfReader(path)
            if len(reader.pages) < 1:
                raise AppError(f"{filename} does not contain a PDF page.")
            page = reader.pages[0]
            info = {
                "token": token,
                "filename": filename,
                "path": str(path),
                "width_pt": float(page.mediabox.width),
                "height_pt": float(page.mediabox.height),
                "width_mm": float(page.mediabox.width) * PT_TO_MM,
                "height_mm": float(page.mediabox.height) * PT_TO_MM,
                "pages": len(reader.pages),
            }
            text = self.label_text(page)
            info.update({"editable":bool(text),"title":text["title"] if text else Path(filename).stem,"specification":text["specification"] if text else ""})
            self.uploads[token] = info
            return public_upload(info)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def remove_upload(self, token: str) -> None:
        info = self.uploads.pop(token, None)
        if info:
            Path(info["path"]).unlink(missing_ok=True)

    def get_upload(self, token: str) -> dict[str, Any]:
        info = self.uploads.get(token)
        if not info or not Path(info["path"]).exists():
            raise AppError("One of the selected label files is no longer available. Please add it again.")
        return info

    def export_library(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            manifest = {
                "format": "atlas-label-template-library",
                "format_version": 1,
                "app_version": APP_VERSION,
                "exported_at": utc_now(),
                "templates": [],
            }
            for meta in self.list_templates():
                template_id = meta["id"]
                folder = self.paths.templates / template_id
                if not (folder / "master.pdf").exists():
                    continue
                manifest["templates"].append(template_id)
                zf.write(folder / "template.json", f"templates/{template_id}/template.json")
                zf.write(folder / "master.pdf", f"templates/{template_id}/master.pdf")
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        return buf.getvalue()

    def import_library(self, data: bytes) -> dict[str, Any]:
        """Restore an exported library as the complete permanent library.

        A dated automatic backup is written first. Importing as a replacement,
        rather than creating duplicates, means renamed, edited, added, and
        deleted templates transfer faithfully between computers.
        """
        staging = self.paths.temp / f"library-import-{uuid.uuid4().hex}"
        staging_templates = staging / "Templates"
        staging_templates.mkdir(parents=True, exist_ok=False)
        imported = 0
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                names = set(zf.namelist())
                if "manifest.json" not in names:
                    raise AppError("This is not an Atlas template-library file.")
                manifest = json.loads(zf.read("manifest.json"))
                if manifest.get("format") != "atlas-label-template-library":
                    raise AppError("Unsupported template-library format.")
                if int(manifest.get("format_version", 0)) != 1:
                    raise AppError("This template library was created by an unsupported version.")

                for template_id in manifest.get("templates", []):
                    safe_id(str(template_id))
                    meta_name = f"templates/{template_id}/template.json"
                    pdf_name = f"templates/{template_id}/master.pdf"
                    if meta_name not in names or pdf_name not in names:
                        raise AppError("The template library is incomplete or damaged.")
                    meta = json.loads(zf.read(meta_name))
                    master_bytes = zf.read(pdf_name)
                    if not master_bytes.startswith(b"%PDF"):
                        raise AppError("The template library contains an invalid master PDF.")
                    meta["id"] = template_id
                    meta["modified_at"] = utc_now()
                    target = staging_templates / template_id
                    target.mkdir(parents=True, exist_ok=False)
                    (target / "master.pdf").write_bytes(master_bytes)
                    (target / "template.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
                    imported += 1

            backup_name = f"Before-Import-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.atlaslabels"
            backup_path = self.paths.backups / backup_name
            backup_path.write_bytes(self.export_library())

            old_templates = self.paths.temp / f"previous-templates-{uuid.uuid4().hex}"
            self.paths.templates.replace(old_templates)
            try:
                staging_templates.replace(self.paths.templates)
            except Exception:
                old_templates.replace(self.paths.templates)
                raise
            shutil.rmtree(old_templates, ignore_errors=True)
            return {"imported": imported, "backup": str(backup_path), "replaced": True}
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        template_id = str(payload.get("template_id", ""))
        template, template_folder = self.get_template(template_id)
        tokens = list(payload.get("label_tokens", []))
        if not tokens:
            raise AppError("Add at least one replacement label PDF.")
        uploads = [self.get_upload(str(t)) for t in tokens]
        validate_label_sizes(template, uploads)

        combine_one_page = bool(payload.get("combine_one_page"))
        make_combined = bool(payload.get("generate_combined"))
        make_individual = bool(payload.get("generate_individual"))
        if not make_combined and not make_individual:
            raise AppError("Select at least one output option.")

        slots = template.get("slots", [])
        if not slots:
            raise AppError("The selected template has no placement positions.")
        if combine_one_page and len(uploads) > len(slots):
            raise AppError(
                f"This template has {len(slots)} positions, so it cannot place {len(uploads)} unique labels on one A5 page."
            )

        output_folder = Path(str(payload.get("output_folder", "")).strip())
        if not output_folder:
            raise AppError("Choose an output folder.")
        output_folder.mkdir(parents=True, exist_ok=True)
        if not output_folder.is_dir():
            raise AppError("The selected output location is not a folder.")

        combined_name = sanitize_filename(
            str(payload.get("combined_name", "Atlas Tool Labels")).strip(),
            default="Atlas Tool Labels",
            force_ext=".pdf",
        )

        self.settings["last_output_folder"] = str(output_folder)
        self.settings["combined_name"] = Path(combined_name).stem
        self._save_settings()

        assignments: list[tuple[str, list[dict[str, Any]]]] = []
        if combine_one_page:
            round_robin = [uploads[i % len(uploads)] for i in range(len(slots))]
            assignments.append((Path(combined_name).stem, round_robin))
        else:
            for upload in uploads:
                assignments.append((Path(upload["filename"]).stem, [upload] * len(slots)))

        master_reader = PdfReader(template_folder / "master.pdf")
        master_page = master_reader.pages[0]

        readers: dict[str, PdfReader] = {}
        pages: dict[str, Any] = {}
        for upload in uploads:
            reader = PdfReader(upload["path"])
            readers[upload["token"]] = reader
            pages[upload["token"]] = reader.pages[0]

        created: list[str] = []
        combined_writer = PdfWriter() if make_combined else None

        for sheet_index, (sheet_name, sheet_uploads) in enumerate(assignments, start=1):
            if combined_writer is not None:
                build_sheet_page(combined_writer, template, master_page, slots, sheet_uploads, pages)

            if make_individual:
                individual_writer = PdfWriter()
                build_sheet_page(individual_writer, template, master_page, slots, sheet_uploads, pages)
                if combine_one_page:
                    filename = sanitize_filename(f"{Path(combined_name).stem} A5 Sheet.pdf", force_ext=".pdf")
                else:
                    filename = sanitize_filename(f"{sheet_name} A5 Sheet.pdf", force_ext=".pdf")
                target = unique_path(output_folder / filename)
                with target.open("wb") as f:
                    individual_writer.write(f)
                created.append(str(target))

        if combined_writer is not None:
            target = unique_path(output_folder / combined_name)
            with target.open("wb") as f:
                combined_writer.write(f)
            created.insert(0, str(target))

        return {
            "created": created,
            "page_count": len(assignments),
            "output_folder": str(output_folder),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_id(value: str) -> None:
    if not re.fullmatch(r"[a-fA-F0-9]{32}", value):
        raise AppError("Invalid template identifier.")


def clean_display_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise AppError("Enter a template name.")
    return value[:100]


def sanitize_filename(value: str, default: str = "output", force_ext: str | None = None) -> str:
    value = Path(value).name
    value = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value).strip(" .")
    if not value:
        value = default
    if force_ext:
        if not force_ext.startswith("."):
            force_ext = "." + force_ext
        value = str(Path(value).with_suffix(force_ext))
    return value[:180]


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 2
    while True:
        candidate = path.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def public_upload(info: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in info.items() if k != "path"}


def matrix_multiply(m1: list[float], m2: list[float]) -> list[float]:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return [
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    ]


def transform_bbox(bbox: list[float], matrix: list[float]) -> list[float]:
    x0, y0, x1, y1 = map(float, bbox)
    a, b, c, d, e, f = matrix
    points = [
        (a * x + c * y + e, b * x + d * y + f)
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    ]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def transform_rect(rect: tuple[float, float, float, float], matrix: list[float]) -> tuple[float, float, float, float]:
    x, y, w, h = rect
    bbox = transform_bbox([x, y, x + w, y + h], matrix)
    return bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]


def analyze_template(path: Path) -> dict[str, Any]:
    try:
        reader = PdfReader(path)
        if len(reader.pages) < 1:
            raise AppError("The template PDF does not contain a page.")
        page = reader.pages[0]
        page_w = float(page.mediabox.width)
        page_h = float(page.mediabox.height)
        is_a5 = (
            abs(page_w - A5_WIDTH_PT) < 3 and abs(page_h - A5_HEIGHT_PT) < 3
        ) or (
            abs(page_h - A5_WIDTH_PT) < 3 and abs(page_w - A5_HEIGHT_PT) < 3
        )

        form_result = detect_form_xobject_slots(reader, page)
        if form_result and len(form_result["slots"]) >= 2:
            result = form_result
        else:
            clip_result = detect_repeated_clip_slots(reader, page)
            if not clip_result or len(clip_result["slots"]) < 2:
                raise AppError(
                    "No repeated linked-PDF positions were detected. The template editor can only start automatically when the PDF contains repeated placed pages or repeated clipping areas."
                )
            result = clip_result

        result.update({
            "page_width_pt": page_w,
            "page_height_pt": page_h,
            "is_a5": is_a5,
        })
        result["slots"] = sort_slots(result["slots"], page_h)
        for idx, slot in enumerate(result["slots"], start=1):
            slot["id"] = slot.get("id") or uuid.uuid4().hex[:12]
            slot["order"] = idx
        return result
    except AppError:
        raise
    except Exception as exc:
        raise AppError(f"Could not analyse the template PDF: {exc}") from exc


def detect_form_xobject_slots(reader: PdfReader, page: Any) -> dict[str, Any] | None:
    resources = page.get("/Resources")
    if resources is None:
        return None
    resources = resources.get_object()
    xobjects = resources.get("/XObject")
    if not xobjects:
        return None
    xobjects = xobjects.get_object()
    content = ContentStream(page.get_contents(), reader)
    ctm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    stack: list[list[float]] = []
    hits: list[dict[str, Any]] = []

    for operands, operator in content.operations:
        op = bytes(operator)
        if op == b"q":
            stack.append(ctm.copy())
        elif op == b"Q":
            ctm = stack.pop() if stack else [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        elif op == b"cm" and len(operands) == 6:
            ctm = matrix_multiply([float(v) for v in operands], ctm)
        elif op == b"Do" and operands:
            obj_ref = xobjects.get(operands[0])
            if obj_ref is None:
                continue
            obj = obj_ref.get_object()
            if obj.get("/Subtype") != "/Form" or not obj.get("/BBox"):
                continue
            bbox = [float(v) for v in obj["/BBox"]]
            form_matrix = [float(v) for v in obj.get("/Matrix", [1, 0, 0, 1, 0, 0])]
            matrix = matrix_multiply(form_matrix, ctm)
            hits.append({
                "bbox": bbox,
                "matrix": matrix,
                "placed_bbox": transform_bbox(bbox, matrix),
            })

    if not hits:
        return None

    groups: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        bbox = hit["bbox"]
        key = (round(abs(bbox[2] - bbox[0]), 2), round(abs(bbox[3] - bbox[1]), 2))
        groups[key].append(hit)
    key, selected = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(selected) < 2:
        return None
    width, height = key
    slots = []
    for hit in selected:
        slots.append({
            "id": uuid.uuid4().hex[:12],
            "matrix": [round(float(v), 10) for v in hit["matrix"]],
            "bbox": [round(float(v), 6) for v in hit["placed_bbox"]],
            "rotation": matrix_rotation(hit["matrix"]),
        })
    return {
        "accepted_width_pt": float(width),
        "accepted_height_pt": float(height),
        "slots": slots,
        "detection_method": "linked PDF positions",
    }


def detect_repeated_clip_slots(reader: PdfReader, page: Any) -> dict[str, Any] | None:
    content = ContentStream(page.get_contents(), reader)
    ctm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    stack: list[tuple[list[float], list[tuple[float, float, float, float]], bool]] = []
    path_rects: list[tuple[float, float, float, float]] = []
    clipping = False
    clip_rects: list[tuple[float, float, float, float]] = []

    paint_ops = {b"n", b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
    for operands, operator in content.operations:
        op = bytes(operator)
        if op == b"q":
            stack.append((ctm.copy(), path_rects.copy(), clipping))
            path_rects = []
            clipping = False
        elif op == b"Q":
            ctm, path_rects, clipping = stack.pop() if stack else (
                [1.0, 0.0, 0.0, 1.0, 0.0, 0.0], [], False
            )
        elif op == b"cm" and len(operands) == 6:
            ctm = matrix_multiply([float(v) for v in operands], ctm)
        elif op == b"re" and len(operands) == 4:
            path_rects.append(transform_rect(tuple(float(v) for v in operands), ctm))
        elif op in (b"W", b"W*"):
            clipping = True
        elif op in paint_ops:
            if clipping:
                clip_rects.extend(path_rects)
            path_rects = []
            clipping = False

    groups: dict[tuple[float, float], dict[tuple[float, float, float, float], tuple[float, float, float, float]]] = defaultdict(dict)
    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)
    for rect in clip_rects:
        x, y, w, h = rect
        if w < 5 or h < 5:
            continue
        if abs(w - page_w) < 2 and abs(h - page_h) < 2:
            continue
        key = (round(w, 1), round(h, 1))
        unique_key = tuple(round(v, 3) for v in rect)
        groups[key][unique_key] = rect
    if not groups:
        return None
    key, group = max(groups.items(), key=lambda kv: len(kv[1]))
    rects = list(group.values())
    if len(rects) < 2:
        return None
    width, height = key
    slots = []
    for x, y, w, h in rects:
        matrix = [1.0, 0.0, 0.0, 1.0, x, y]
        slots.append({
            "id": uuid.uuid4().hex[:12],
            "matrix": [round(float(v), 10) for v in matrix],
            "bbox": [round(x, 6), round(y, 6), round(x + w, 6), round(y + h, 6)],
            "rotation": 0,
        })
    return {
        "accepted_width_pt": float(width),
        "accepted_height_pt": float(height),
        "slots": slots,
        "detection_method": "repeated placement areas",
    }


def matrix_rotation(matrix: list[float]) -> int:
    a, b, c, d, _, _ = matrix
    angle = math.degrees(math.atan2(b, a)) % 360
    return int(round(angle / 90.0) * 90) % 360


def sort_slots(slots: list[dict[str, Any]], page_height: float) -> list[dict[str, Any]]:
    def key(slot: dict[str, Any]) -> tuple[float, float]:
        bbox = slot.get("bbox") or transform_bbox([0, 0, 1, 1], slot["matrix"])
        x0, y0, x1, y1 = bbox
        visual_top = page_height - y1
        return (round(visual_top, 2), round(x0, 2))
    return sorted(slots, key=key)


def validate_slots(slots_payload: Any, template: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(slots_payload, list):
        raise AppError("Invalid placement-position data.")
    page_w = float(template["page_width_pt"])
    page_h = float(template["page_height_pt"])
    accepted_w = float(template["accepted_width_pt"])
    accepted_h = float(template["accepted_height_pt"])
    result: list[dict[str, Any]] = []
    for index, item in enumerate(slots_payload):
        if not isinstance(item, dict):
            raise AppError("Invalid placement-position data.")
        matrix = item.get("matrix")
        if not isinstance(matrix, list) or len(matrix) != 6:
            raise AppError("Each placement position requires a six-value transform matrix.")
        matrix = [float(v) for v in matrix]
        bbox = transform_bbox([0, 0, accepted_w, accepted_h], matrix)
        # Allow positions to touch the page edge, but not be wildly outside the sheet.
        if bbox[2] < -5 or bbox[0] > page_w + 5 or bbox[3] < -5 or bbox[1] > page_h + 5:
            raise AppError(f"Placement position {index + 1} is outside the page.")
        result.append({
            "id": re.sub(r"[^a-zA-Z0-9_-]", "", str(item.get("id", "")))[:24] or uuid.uuid4().hex[:12],
            "matrix": [round(v, 10) for v in matrix],
            "bbox": [round(v, 6) for v in bbox],
            "rotation": matrix_rotation(matrix),
            "order": index + 1,
        })
    return sort_slots(result, page_h)


def validate_label_sizes(template: dict[str, Any], uploads: list[dict[str, Any]]) -> None:
    expected_w = float(template["accepted_width_pt"])
    expected_h = float(template["accepted_height_pt"])
    tolerance = 0.75
    errors = []
    for upload in uploads:
        w = float(upload["width_pt"])
        h = float(upload["height_pt"])
        if abs(w - expected_w) > tolerance or abs(h - expected_h) > tolerance:
            errors.append(
                f"{upload['filename']} is {w * PT_TO_MM:.2f} x {h * PT_TO_MM:.2f} mm"
            )
    if errors:
        expected = f"{expected_w * PT_TO_MM:.2f} x {expected_h * PT_TO_MM:.2f} mm"
        raise AppError(
            "The selected template accepts " + expected + ". These files do not match: " + "; ".join(errors)
        )


def build_sheet_page(
    writer: PdfWriter,
    template: dict[str, Any],
    master_page: Any,
    slots: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    pages: dict[str, Any],
) -> Any:
    # Keep any static artwork, registration marks, or background content from
    # the saved master. Replacement labels are placed exactly over the stored
    # label positions, matching a relink operation while remaining independent
    # of Illustrator.
    page = writer.add_page(master_page)
    for slot, upload in zip(slots, assignments):
        source_page = pages[upload["token"]]
        page.merge_transformed_page(source_page, slot["matrix"], over=True, expand=False)
    add_cut_contour_border(page, writer)
    return page


def add_cut_contour_border(page: Any, writer: PdfWriter) -> None:
    resources = page.get("/Resources")
    if resources is None:
        resources = DictionaryObject()
        page[NameObject("/Resources")] = resources
    else:
        resources = resources.get_object()
    color_spaces = resources.get("/ColorSpace")
    if color_spaces is None:
        color_spaces = DictionaryObject()
        resources[NameObject("/ColorSpace")] = color_spaces
    else:
        color_spaces = color_spaces.get_object()

    tint_function = DictionaryObject({
        NameObject("/FunctionType"): NumberObject(2),
        NameObject("/Domain"): ArrayObject([NumberObject(0), NumberObject(1)]),
        NameObject("/C0"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0), NumberObject(0)]),
        NameObject("/C1"): ArrayObject([FloatObject(0.11), NumberObject(1), NumberObject(0), NumberObject(0)]),
        NameObject("/N"): NumberObject(1),
        NameObject("/Range"): ArrayObject([
            NumberObject(0), NumberObject(1), NumberObject(0), NumberObject(1),
            NumberObject(0), NumberObject(1), NumberObject(0), NumberObject(1),
        ]),
    })
    color_spaces[NameObject("/ATCutContour")] = ArrayObject([
        NameObject("/Separation"),
        NameObject("/CutContour"),
        NameObject("/DeviceCMYK"),
        tint_function,
    ])

    content = ContentStream(page.get_contents(), writer)
    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)
    content.operations += [
        ([], b"q"),
        ([NameObject("/ATCutContour")], b"CS"),
        ([NumberObject(1)], b"SCN"),
        ([NumberObject(1)], b"w"),
        ([NumberObject(0)], b"J"),
        ([NumberObject(0)], b"j"),
        ([FloatObject(0.5), FloatObject(0.5), FloatObject(page_w - 1), FloatObject(page_h - 1)], b"re"),
        ([], b"S"),
        ([], b"Q"),
    ]
    page.replace_contents(content)


def choose_output_folder(initial: str) -> str:
    if os.name != "nt":
        return initial
    initial_escaped = initial.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description='Choose where the generated PDF files will be saved';"
        f"$d.SelectedPath='{initial_escaped}';"
        "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){"
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
        "Write-Output $d.SelectedPath}"
    )
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=startupinfo,
        timeout=120,
    )
    return completed.stdout.strip()


def open_folder(path: str) -> None:
    folder = Path(path)
    if not folder.exists():
        raise AppError("The output folder no longer exists.")
    if os.name == "nt":
        os.startfile(str(folder))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(folder)])


class AtlasHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], state: AppState):
        super().__init__(server_address, handler)
        self.state = state


class Handler(BaseHTTPRequestHandler):
    server_version = "AtlasLabelBuilder/1.0"

    @property
    def state(self) -> AppState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/status":
                self.send_json({
                    "app_name": APP_NAME,
                    "version": APP_VERSION,
                    "settings": self.state.settings,
                    "data_root": str(self.state.paths.root),
                })
            elif path == "/api/tool-templates":
                self.send_json(self.state.tool_templates())
            elif path == "/api/designer":
                self.send_json(self.state.designer_info())
            elif path == "/api/templates":
                self.send_json({"templates": self.state.list_templates()})
            elif path.startswith("/api/templates/") and path.endswith("/master.pdf"):
                template_id = path.split("/")[3]
                _, folder = self.state.get_template(template_id)
                self.send_file(folder / "master.pdf", "application/pdf")
            elif path == "/api/ping":
                self.state.last_heartbeat = time.time()
                self.send_json({"ok": True})
            elif path == "/":
                self.send_file(APP_DIR / "static" / "index.html", "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                rel = path[len("/static/"):]
                if ".." in rel or rel.startswith("/"):
                    raise AppError("Invalid file path.")
                target = APP_DIR / "static" / rel
                mime = mime_for(target)
                self.send_file(target, mime)
            elif path.startswith("/label-assets/"):
                rel = path[len("/label-assets/"):]
                if ".." in rel or rel.startswith("/"):
                    raise AppError("Invalid file path.")
                target = APP_DIR / "label_assets" / rel
                mime = mime_for(target)
                self.send_file(target, mime)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.handle_exception(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/tool-templates/folder":
                payload=self.read_json()
                folder=payload.get('folder')
                if folder is None:folder=choose_output_folder(str(self.state.tool_folder()))
                if folder:
                    target=Path(folder).expanduser().resolve()
                    if not target.is_dir():raise AppError('Choose an existing folder.')
                    with self.state.lock:
                        self.state.settings['tool_template_folder']=str(target)
                        self.state._save_settings()
                    self.send_json(self.state.tool_templates())
                else:self.send_json({'cancelled':True})
            elif path == "/api/designer/font":
                self.state.designer_font(self.read_body())
                self.send_json({"ok": True})
            elif path == "/api/designer/preview":
                payload=self.read_json()
                if payload.get('source_token') and not payload.get('editable',True):
                    data=Path(self.state.get_upload(payload['source_token'])['path']).read_bytes()
                else:data, sizes = self.state.designer_pdf(payload)
                self.send_bytes(data, "application/pdf")
            elif path == "/api/designer/add":
                self.send_json(self.state.designer_add(self.read_json()), status=201)
            elif path == "/api/templates/upload":
                data = self.read_body()
                filename = unquote(self.headers.get("X-Filename", "template.pdf"))
                name = unquote(self.headers.get("X-Template-Name", Path(filename).stem))
                meta = self.state.create_template(name, data, filename)
                self.send_json({"template": meta}, status=201)
            elif path.startswith("/api/templates/") and path.endswith("/replace-master"):
                template_id = path.split("/")[3]
                data = self.read_body()
                filename = unquote(self.headers.get("X-Filename", "template.pdf"))
                meta = self.state.replace_template_master(template_id, data, filename)
                self.send_json({"template": meta})
            elif path.startswith("/api/templates/") and path.endswith("/duplicate"):
                template_id = path.split("/")[3]
                meta = self.state.duplicate_template(template_id)
                self.send_json({"template": meta}, status=201)
            elif path == "/api/labels/upload":
                data = self.read_body()
                filename = unquote(self.headers.get("X-Filename", "label.pdf"))
                info = self.state.store_label_upload(filename, data)
                self.send_json({"upload": info}, status=201)
            elif path == "/api/templates/export":
                data = self.state.export_library()
                filename = f"Atlas-Label-Templates-{datetime.now().strftime('%Y-%m-%d')}.atlaslabels"
                self.send_bytes(
                    data,
                    "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )
            elif path == "/api/templates/import":
                data = self.read_body()
                result = self.state.import_library(data)
                self.send_json(result)
            elif path == "/api/select-output-folder":
                payload = self.read_json()
                initial = str(payload.get("initial", self.state.settings.get("last_output_folder", "")))
                folder = choose_output_folder(initial)
                self.send_json({"folder": folder})
            elif path == "/api/generate":
                payload = self.read_json()
                result = self.state.generate_rows(payload)
                self.send_json(result)
            elif path == "/api/open-folder":
                payload = self.read_json()
                open_folder(str(payload.get("path", "")))
                self.send_json({"ok": True})
            elif path == "/api/shutdown":
                self.send_json({"ok": True})
                self.state.shutdown_requested.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.handle_exception(exc)

    def do_PUT(self) -> None:
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/templates/"):
                template_id = path.split("/")[3]
                payload = self.read_json()
                meta = self.state.update_template(template_id, payload)
                self.send_json({"template": meta})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.handle_exception(exc)

    def do_DELETE(self) -> None:
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/templates/"):
                template_id = path.split("/")[3]
                self.state.delete_template(template_id)
                self.send_json({"ok": True})
            elif path.startswith("/api/labels/"):
                token = path.split("/")[3]
                self.state.remove_upload(token)
                self.send_json({"ok": True})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.handle_exception(exc)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise AppError("No file or data was received.")
        if length > UPLOAD_LIMIT:
            raise AppError("The selected file is too large.")
        data = self.rfile.read(length)
        if len(data) != length:
            raise AppError("The upload was interrupted.")
        return data

    def read_json(self) -> dict[str, Any]:
        raw = self.read_body()
        try:
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            return payload
        except Exception as exc:
            raise AppError("Invalid request data.") from exc

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(data, "application/json; charset=utf-8", status=status)

    def send_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_bytes(data, content_type)

    def send_bytes(
        self,
        data: bytes,
        content_type: str,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def handle_exception(self, exc: Exception) -> None:
        if isinstance(exc, AppError):
            message = str(exc)
            status = 400
        else:
            traceback.print_exc()
            message = f"Unexpected error: {exc}"
            status = 500
        try:
            self.send_json({"error": message}, status=status)
        except Exception:
            pass


def mime_for(path: Path) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".wasm": "application/wasm",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".pdf": "application/pdf",
    }.get(path.suffix.lower(), "application/octet-stream")


def idle_monitor(server: AtlasHTTPServer, state: AppState) -> None:
    while not state.shutdown_requested.wait(15):
        # The front end sends a heartbeat. Auto-close orphaned background servers.
        if time.time() - state.last_heartbeat > 150:
            state.shutdown_requested.set()
            server.shutdown()
            return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    paths = AppPaths.create(Path(args.data_root).resolve())
    state = AppState(paths)
    server = AtlasHTTPServer(("127.0.0.1", args.port), Handler, state)
    port = server.server_address[1]
    print(f"PORT={port}", flush=True)
    if args.open_browser:threading.Timer(.5,lambda:webbrowser.open(f"http://127.0.0.1:{port}")).start()
    threading.Thread(target=idle_monitor, args=(server, state), daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
