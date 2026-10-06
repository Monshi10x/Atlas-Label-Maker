import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from atlas_label_maker import AppPaths, AppState, PdfReader, PdfWriter
from pdf_export import export_label_pdf, export_options, prepare_export_parts
from pypdf.generic import ArrayObject, ContentStream, DecodedStreamObject, DictionaryObject, NameObject, TextStringObject
from test_exports import cut_strokes, image_refs, simple_label


def text_label(marker=True):
    writer = PdfWriter()
    page = writer.add_page(PdfReader(io.BytesIO(simple_label())).pages[0])
    page['/Resources'][NameObject('/Font')] = DictionaryObject({NameObject('/AtlasText'): writer._add_object(DictionaryObject({
        NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))})
    text = b'q 0 g BT /AtlasText 8 Tf 1 0 0 1 15 20 Tm (CREATED TEXT) Tj ET Q'
    if marker:
        text = b'/AtlasCreatedText BMC\n' + text + b'\nEMC'
    content = ContentStream(page.get_contents(), writer)
    content.set_data(content.get_data() + b'\n' + text)
    page.replace_contents(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def layer_names(pdf):
    return [ref.get_object()['/Name'] for ref in pdf.trailer['/Root']['/OCProperties']['/OCGs']]


def visible_pixels(data, hidden):
    import pypdfium2 as pdfium
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(io.BytesIO(data)))
    config = writer._root_object['/OCProperties']
    config['/D'][NameObject('/ON')] = ArrayObject(ref for ref in config['/OCGs'] if ref.get_object()['/Name'] not in hidden)
    config['/D'][NameObject('/OFF')] = ArrayObject(ref for ref in config['/OCGs'] if ref.get_object()['/Name'] in hidden)
    output = io.BytesIO()
    writer.write(output)
    with pdfium.PdfDocument(output.getvalue()) as document:
        page = document[0]
        try:
            bitmap = page.render(scale=1, rev_byteorder=True, force_bitmap_format=pdfium.raw.FPDFBitmap_BGR)
            try:
                data = bytes(bitmap.buffer)
                return b''.join(data[y*bitmap.stride:y*bitmap.stride+bitmap.width*3] for y in range(bitmap.height))
            finally:
                bitmap.close()
        finally:
            page.close()


class LayerTests(unittest.TestCase):
    def test_sheet_modes_perimeter_and_layer_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            state = AppState(AppPaths.create(Path(directory)))
            source = text_label()
            upload = state.store_label_upload('New.pdf', source)
            slots = state.get_template('1'*32)[0]['slot_count']
            for raster in (False, True):
                for raster_text in (False, True):
                    for perimeter in (False, True):
                        with self.subTest(raster=raster, raster_text=raster_text, perimeter=perimeter):
                            result = state.generate({'template_id':'1'*32, 'label_tokens':[upload['token']],
                                'generate_combined':True, 'generate_individual':True, 'rasterize':raster,
                                'rasterize_text':raster_text, 'a5_cut_contour':perimeter, 'output_folder':str(Path(directory)/'out')})
                            for filename in result['created']:
                                pdf = PdfReader(filename)
                                self.assertEqual(layer_names(pdf), ['artwork', 'cut'])
                                page = pdf.pages[0]
                                self.assertEqual(cut_strokes(page), slots + int(perimeter))
                                self.assertEqual('CREATED TEXT' in page.extract_text(), not raster or not raster_text)
                                self.assertEqual(len(image_refs(page)), int(raster))
                                # Every placement form belongs to exactly one
                                # layer. Artwork has zero cut paints; cut forms
                                # contain no text, images or artwork paints.
                                for ref in page['/Resources']['/XObject'].values():
                                    form = ref.get_object()
                                    self.assertIn(form['/OC']['/Name'], ('artwork', 'cut'))
                                    probe = PdfWriter()
                                    component = probe.add_blank_page(width=155.9, height=42.52)
                                    component[NameObject('/Resources')] = form['/Resources']
                                    component[NameObject('/Contents')] = ref
                                    if form['/OC']['/Name'] == 'artwork':
                                        self.assertEqual(cut_strokes(component), 0)
                                    else:
                                        self.assertEqual(cut_strokes(component), 1)
                                        self.assertEqual(component.extract_text(), '')
                                        self.assertEqual(len(image_refs(component)), 0)
                                ops = ContentStream(page.get_contents(), pdf).operations
                                border_layer = None
                                for args, op in ops:
                                    if op == b'BDC':
                                        border_layer = args[1]
                                    elif op == b'EMC':
                                        border_layer = None
                                    elif op == b'S':
                                        self.assertTrue(perimeter)
                                        self.assertEqual(border_layer, '/CutLayer')
            self.assertEqual(Path(state.get_upload(upload['token'])['path']).read_bytes(), source)

    def test_created_text_can_stay_vector_without_being_baked_into_image(self):
        for marker in (False, True):
            source = PdfReader(io.BytesIO(text_label(marker))).pages[0]
            for raster_text in (False, True):
                parts = prepare_export_parts(source, True, 300, raster_text)
                self.assertEqual('CREATED TEXT' in parts['artwork'].extract_text(), not raster_text)
                images = [ref.get_object() for ref in parts['artwork']['/Resources']['/XObject'].values() if ref.get_object().get('/Subtype') == '/Image']
                self.assertEqual(len(images), 1)
                image = images[0]
                solid_yellow = b'\xff\xff\x00' * (image['/Width'] * image['/Height'])
                if raster_text:
                    self.assertNotEqual(image.get_data(), solid_yellow)
                else:
                    self.assertEqual(image.get_data(), solid_yellow)
                self.assertEqual(cut_strokes(parts['artwork']), 0)
                self.assertEqual(cut_strokes(parts['cut']), 1)

    def test_real_pdf_layers_can_be_hidden_independently(self):
        page = PdfReader(io.BytesIO(text_label())).pages[0]
        for raster, raster_text in ((False, False), (True, False), (True, True)):
            data = export_label_pdf(page, raster, 300, raster_text)
            pdf = PdfReader(io.BytesIO(data))
            self.assertEqual(layer_names(pdf), ['artwork', 'cut'])
            self.assertEqual(cut_strokes(pdf.pages[0]), 1)
            everything = visible_pixels(data, set())
            artwork = visible_pixels(data, {'cut'})
            cuts = visible_pixels(data, {'artwork'})
            nothing = visible_pixels(data, {'artwork', 'cut'})
            self.assertNotEqual(everything, artwork)
            self.assertNotEqual(everything, cuts)
            self.assertNotEqual(artwork, cuts)
            self.assertEqual(nothing, b'\xff' * len(nothing))

    def test_layers_are_shared_across_pages_and_options_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            state = AppState(AppPaths.create(Path(directory)))
            uploads = [state.store_label_upload(f'{i}.pdf', text_label()) for i in range(2)]
            result = state.generate({'template_id':'1'*32, 'label_tokens':[upload['token'] for upload in uploads],
                'generate_combined':True, 'rasterize_text':False, 'a5_cut_contour':False, 'output_folder':directory})
            pdf = PdfReader(result['created'][0])
            self.assertEqual(len(pdf.pages), 2)
            self.assertEqual(layer_names(pdf), ['artwork', 'cut'])
            for page in pdf.pages:
                for name in ('/ArtworkLayer', '/CutLayer'):
                    ref = page['/Resources']['/Properties'].raw_get(name)
                    self.assertIn(ref, pdf.trailer['/Root']['/OCProperties']['/OCGs'])
            restored = AppState(AppPaths.create(Path(directory)))
            self.assertFalse(restored.settings['rasterize_text'])
            self.assertFalse(restored.settings['a5_cut_contour'])
            for key in ('rasterize_text', 'a5_cut_contour'):
                for bad in ('false', 0, None):
                    with self.assertRaises(ValueError):
                        export_options({key:bad})

    def test_nested_created_text_and_old_source_layers_are_reassigned(self):
        source_writer = PdfWriter()
        page = source_writer.add_page(PdfReader(io.BytesIO(text_label())).pages[0])
        old = source_writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/OCG'), NameObject('/Name'):TextStringObject('old source')}))
        source_writer._root_object[NameObject('/OCProperties')] = DictionaryObject({NameObject('/OCGs'):ArrayObject([old]),
            NameObject('/D'):DictionaryObject({NameObject('/ON'):ArrayObject([old])})})
        fonts = page['/Resources']['/Font']
        fonts[NameObject('/RenamedCreatedFont')] = fonts.pop('/AtlasText')
        form = DecodedStreamObject()
        form.update({NameObject('/Type'):NameObject('/XObject'), NameObject('/Subtype'):NameObject('/Form'),
            NameObject('/BBox'):page.mediabox, NameObject('/Resources'):page['/Resources'], NameObject('/OC'):old})
        form.set_data(page.get_contents().get_data().replace(b'/AtlasText', b'/RenamedCreatedFont'))
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Original'):source_writer._add_object(form)}),
            NameObject('/Properties'):DictionaryObject({NameObject('/OldLayer'):old})})
        content = DecodedStreamObject()
        content.set_data(b'/OC /OldLayer BDC /Original Do EMC')
        page[NameObject('/Contents')] = source_writer._add_object(content)
        buffer = io.BytesIO()
        source_writer.write(buffer)
        original = PdfReader(io.BytesIO(buffer.getvalue()))
        pdf = PdfReader(io.BytesIO(export_label_pdf(original.pages[0], True, 300, False)))
        self.assertEqual(layer_names(pdf), ['artwork', 'cut'])
        self.assertEqual(layer_names(original), ['old source'])
        self.assertIn('CREATED TEXT', pdf.pages[0].extract_text())
        self.assertEqual(cut_strokes(pdf.pages[0]), 1)
        self.assertEqual(len(image_refs(pdf.pages[0])), 1)
        def inspect(resources, top=True):
            self.assertNotIn('/OldLayer', resources.get('/Properties', {}))
            for ref in resources.get('/XObject', {}).values():
                obj = ref.get_object()
                if obj.get('/Subtype') == '/Form':
                    if top:
                        self.assertIn(obj['/OC']['/Name'], ('artwork', 'cut'))
                    else:
                        self.assertNotIn('/OC', obj)
                    inspect(obj['/Resources'], False)
                elif obj.get('/Subtype') == '/Image':
                    self.assertNotIn('/OC', obj)
                    self.assertEqual(obj.get_data(), b'\xff\xff\x00' * (obj['/Width'] * obj['/Height']))
        inspect(pdf.pages[0]['/Resources'])


if __name__ == '__main__':
    unittest.main()
