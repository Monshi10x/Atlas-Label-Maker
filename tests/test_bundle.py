import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('build_bundle', Path(__file__).resolve().parents[1] / 'launcher' / 'build_bundle.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BundleTests(unittest.TestCase):
    def test_portable_paths_include_renderer_licenses_and_skip_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'app'
            files = {
                'atlas_label_maker.py': b'app',
                'vendor/pypdfium2_raw/pdfium.dll': b'renderer',
                'vendor/pypdfium2-5.3.0.dist-info/licenses/LICENSES/Apache-2.0.txt': b'license',
                'vendor/pypdfium2-5.3.0.dist-info/licenses/data/windows_x64/BUILD_LICENSES/pdfium.txt': b'pdfium license',
                'vendor/pypdfium2/__pycache__/test.pyc': b'cache',
            }
            for name, data in files.items():
                target = app / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            destination = root / 'launcher' / 'app_bundle.zip'
            builder.build_bundle(app, destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(set(archive.namelist()), {name for name in files if '__pycache__' not in name})
                self.assertFalse(any('\\' in entry.filename or entry.is_dir() for entry in archive.infolist()))
                for name, data in files.items():
                    if '__pycache__' not in name:
                        self.assertEqual(archive.read(name), data)
            # Refresh replaces a complete archive and leaves no temporary files.
            (app / 'atlas_label_maker.py').write_bytes(b'updated')
            builder.build_bundle(app, destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.read('atlas_label_maker.py'), b'updated')
            self.assertEqual(list(destination.parent.iterdir()), [destination])


if __name__ == '__main__':
    unittest.main()
