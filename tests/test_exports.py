import io
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from atlas_label_maker import AppError, AppPaths, AppState, PdfReader, PdfWriter, add_cut_contour_border
from label_designer import create_label
from pdf_export import export_options, rasterize_artwork
from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject, NameObject


def cut_strokes(page):
    """Count actual spot-colour painting operations, including nested forms."""
    def count(owner, resources, initial=False):
        resources = owner.get('/Resources', resources).get_object()
        stream = ContentStream(owner if owner.get('/Subtype') == '/Form' else owner.get_contents(), page.pdf)
        spot, stack, total = initial, [], 0
        for args, op in stream.operations:
            if op == b'q':
                stack.append(spot)
            elif op == b'Q' and stack:
                spot = stack.pop()
            elif op == b'CS':
                cs = resources.get('/ColorSpace', {}).get(args[0])
                cs = cs.get_object() if cs else None
                spot = bool(cs and cs[0] == '/Separation' and cs[1] == '/CutContour')
            elif op in (b'G', b'RG', b'K'):
                spot = False
            elif op in (b'S', b's', b'B', b'B*', b'b', b'b*') and spot:
                total += 1
            elif op == b'Do':
                form = resources['/XObject'][args[0]].get_object()
                if form.get('/Subtype') == '/Form':
                    total += count(form, resources, spot)
        return total
    return count(page, page['/Resources'])


def simple_label(size=55, nested=False):
    """Yellow artwork and an interior magenta spot cutter: easy to inspect."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=size * 72 / 25.4, height=(15 if size == 55 else size) * 72 / 25.4)
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    add_cut_contour_border(page, writer)
    cs = page['/Resources']['/ColorSpace']['/ATCutContour']
    content = DecodedStreamObject()
    content.set_data(f'q 1 1 0 rg 0 0 {w} {h} re f /ATCutContour CS 1 SCN 2 w 8 8 {w-16} {h-16} re S Q'.encode())
    page[NameObject('/Contents')] = writer._add_object(content)
    if nested:
        form = DecodedStreamObject()
        form.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                     NameObject('/BBox'): page.mediabox, NameObject('/Resources'): page['/Resources']})
        # The form inherits the CutContour stroke colour from its caller.
        form.set_data(f'1 1 0 rg 0 0 {w} {h} re f 2 w 8 8 {w-16} {h-16} re S'.encode())
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/ColorSpace'): DictionaryObject({NameObject('/ATCutContour'): cs}),
                                                          NameObject('/XObject'): DictionaryObject({NameObject('/Artwork'): writer._add_object(form)})})
        content.set_data(b'q /ATCutContour CS 1 SCN /Artwork Do Q')
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_refs(page):
    images, visited = set(), set()
    def visit(resources):
        for ref in resources.get('/XObject', {}).values():
            identity = (ref.idnum, ref.generation)
            if identity in visited:
                continue
            visited.add(identity)
            obj = ref.get_object()
            if obj.get('/Subtype') == '/Image':
                images.add(identity)
            elif obj.get('/Subtype') == '/Form':
                visit(obj.get('/Resources', resources))
    visit(page['/Resources'])
    return images


class ExportTests(unittest.TestCase):
    def test_master_artwork_and_old_cuts_are_absent_in_both_layouts(self):
        with tempfile.TemporaryDirectory() as folder:
            state = AppState(AppPaths.create(Path(folder)))
            for template_id, size, original in [('1'*32, 55, 'Compression Spiral'), ('2'*32, 35, 'ER32 COLLET')]:
                source = simple_label(size)
                upload = state.store_label_upload('New label.pdf', source)
                for raster in (False, True):
                    result = state.generate({'template_id': template_id, 'label_tokens': [upload['token']],
                                             'rasterize': raster, 'generate_combined': True, 'generate_individual': True,
                                             'output_folder': str(Path(folder)/'out')})
                    slots = state.get_template(template_id)[0]['slot_count']
                    self.assertEqual(len(result['created']), 2)
                    for output in result['created']:
                        page = PdfReader(output).pages[0]
                        self.assertNotIn(original, page.extract_text())
                        self.assertEqual(cut_strokes(page), slots + 1)
                        self.assertAlmostEqual(float(page.mediabox.width), 148*72/25.4, places=3)
                        self.assertEqual(len(image_refs(page)), 1 if raster else 0)
                        self.assertEqual(len(page['/Resources']['/XObject']), 1)
                    self.assertEqual(Path(state.get_upload(upload['token'])['path']).read_bytes(), source)

    def test_raster_dpi_and_cut_lines_not_baked_into_image(self):
        for nested in (False, True):
            source = PdfReader(io.BytesIO(simple_label(nested=nested))).pages[0]
            for dpi in (150, 300, 600):
                page = rasterize_artwork(source, dpi)
                self.assertEqual(cut_strokes(page), 1)
                images = [ref.get_object() for ref in page['/Resources']['/XObject'].values()
                          if ref.get_object().get('/Subtype') == '/Image']
                self.assertEqual(len(images), 1)
                image = images[0]
                self.assertEqual(image['/Width'], math.ceil(55*72/25.4*dpi/72))
                self.assertEqual(image['/Height'], math.ceil(15*72/25.4*dpi/72))
                pixels = image.get_data()
                # Every image pixel is yellow. The magenta cutter exists only
                # in the PDF's vector painting commands, including nested forms.
                self.assertEqual(pixels, b'\xff\xff\x00' * (image['/Width'] * image['/Height']))
                self.assertEqual(cut_strokes(source), 1)

    def test_default_raster_and_vector_opt_out_preserve_edited_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            state = AppState(AppPaths.create(Path(folder)))
            original, _ = create_label({'title': 'ORIGINAL', 'specification': '3x12 DLC'})
            upload = state.store_label_upload('Label.pdf', original)
            rows = [{'source_token': upload['token'], 'editable': True, 'title': title, 'specification': '6x15 DLC'}
                    for title in ('FIRST EDIT', 'SECOND EDIT')]
            options = {'template_id': '1'*32, 'generate_combined': True, 'output_folder': str(Path(folder)/'out'), 'label_rows': rows}
            raster = PdfReader(state.generate_rows(options)['created'][0])
            self.assertEqual(len(raster.pages), 2)
            self.assertTrue(state.settings['rasterize'])
            self.assertEqual(state.settings['raster_dpi'], 300)
            for page in raster.pages:
                self.assertEqual(page.extract_text(), '')
                self.assertEqual(cut_strokes(page), state.get_template('1'*32)[0]['slot_count']+1)
            vector = PdfReader(state.generate_rows({**options, 'rasterize': False, 'raster_dpi': 'unused'})['created'][0])
            for index, page in enumerate(vector.pages):
                self.assertIn(rows[index]['title'], page.extract_text())
                self.assertNotIn(rows[1-index]['title'], page.extract_text())
                self.assertNotIn('Compression Spiral', page.extract_text())
                self.assertNotIn('ORIGINAL', page.extract_text())
            mixed = PdfReader(state.generate_rows({**options, 'combine_one_page': True})['created'][0])
            self.assertEqual(len(image_refs(mixed.pages[0])), 2)
            self.assertEqual(len(mixed.pages[0]['/Resources']['/XObject']), 2)
            self.assertEqual(len(state.uploads), 1)
            self.assertEqual(Path(state.get_upload(upload['token'])['path']).read_bytes(), original)

    def test_dpi_validation_prevents_output_and_vector_does_not_need_dpi(self):
        self.assertEqual(export_options({}), (True, 300))
        self.assertEqual(export_options({'rasterize': False, 'raster_dpi': None}), (False, None))
        with tempfile.TemporaryDirectory() as folder:
            state = AppState(AppPaths.create(Path(folder)))
            upload = state.store_label_upload('Label.pdf', simple_label())
            output = Path(folder)/'out'
            for dpi in (0, -1, 71, 1201, 300.5, True, '300', None, float('nan'), float('inf')):
                with self.assertRaises(AppError):
                    state.generate({'template_id': '1'*32, 'label_tokens': [upload['token']], 'generate_combined': True,
                                    'output_folder': str(output), 'raster_dpi': dpi})
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
