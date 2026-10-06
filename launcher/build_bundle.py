"""Create a portable application ZIP, including renderer license notices."""
from pathlib import Path
import os
import tempfile
import zipfile


def build_bundle(app_dir, destination):
    app_dir = Path(app_dir)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='app_bundle-', suffix='.tmp', dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(app_dir.rglob('*')):
                relative = source.relative_to(app_dir)
                if '__pycache__' in relative.parts or source.suffix == '.pyc':
                    continue
                if source.is_file():
                    # Files only: the launcher creates parents as needed. ZIP
                    # paths use forward slashes on Windows as well as Linux.
                    archive.write(source, relative.as_posix())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    build_bundle(root / 'app', root / 'launcher' / 'app_bundle.zip')
