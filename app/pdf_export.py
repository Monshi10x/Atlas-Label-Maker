"""Raster artwork independently of vector CutContour paths."""
import io
import math

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import (
    ArrayObject, ContentStream, DecodedStreamObject, DictionaryObject,
    NameObject, NumberObject, RectangleObject, TextStringObject,
)


def export_options(payload):
    rasterize = payload.get('rasterize', True)
    if not isinstance(rasterize, bool):
        raise ValueError('Rasterize must be enabled or disabled.')
    for key, label in (('rasterize_text', 'Rasterize created text'), ('a5_cut_contour', 'A5 perimeter cut contour')):
        if not isinstance(payload.get(key, True), bool):
            raise ValueError(label + ' must be enabled or disabled.')
    dpi = payload.get('raster_dpi', 300)
    if rasterize:
        if isinstance(dpi, bool) or not isinstance(dpi, (int, float)) or not math.isfinite(dpi) or int(dpi) != dpi or not 72 <= dpi <= 1200:
            raise ValueError('Raster resolution must be a whole number from 72 to 1200 DPI.')
        dpi = int(dpi)
    return rasterize, dpi


def _cut_color(resources, name):
    space = resources.get('/ColorSpace', {}).get(name)
    if space is None:
        return False
    space = space.get_object()
    if not isinstance(space, ArrayObject):
        return False
    if space[0] == '/Separation':
        return str(space[1]).lower() == '/cutcontour'
    if space[0] == '/DeviceN':
        return any(str(color).lower() == '/cutcontour' for color in space[1])
    return False


def _filter_content(owner, writer, cuts, inherited=(False, False, None), parent_resources=None, depth=0, text_mode='all', created_scope=False):
    """Keep graphics state/clipping intact while separating paint operations.

    Form XObjects are filtered per invocation, because the same form can inherit
    different spot colours from its callers. Source objects belong to a cloned
    writer, so neither uploads nor the other export mode are modified.
    """
    if depth > 30:
        raise ValueError('PDF forms are nested too deeply to rasterize safely.')
    resources = owner.get('/Resources', parent_resources or DictionaryObject()).get_object()
    # Local resources prevent a form invocation from changing its caller.
    resources = DictionaryObject(resources)
    owner[NameObject('/Resources')] = resources
    owner.pop('/OC', None)
    xobjects = DictionaryObject(resources.get('/XObject', {}).get_object()) if '/XObject' in resources else DictionaryObject()
    resources[NameObject('/XObject')] = xobjects
    stream = ContentStream(owner if owner.get('/Subtype') == '/Form' else owner.get_contents(), writer)
    stroke, fill, font = inherited
    stack, operations = [], []
    marked_stack = []
    used_xobjects, used_fonts, used_shadings, used_properties = set(), set(), set(), set()
    stroke_ops = {b'S', b's'}
    fill_ops = {b'f', b'F', b'f*'}
    both_ops = {b'B', b'B*', b'b', b'b*'}
    for args, op in stream.operations:
        if op in (b'BMC', b'BDC'):
            keep = not (op == b'BDC' and args[0] == '/OC')
            marked_stack.append((created_scope, keep))
            created_scope = created_scope or args[0] == '/AtlasCreatedText'
            if not keep:
                continue
            if op == b'BDC' and isinstance(args[1], NameObject):
                used_properties.add(args[1])
        elif op == b'EMC' and marked_stack:
            created_scope, keep = marked_stack.pop()
            if not keep:
                continue
        if op == b'q':
            stack.append((stroke, fill, font))
        elif op == b'Q' and stack:
            stroke, fill, font = stack.pop()
        elif op == b'CS':
            stroke = _cut_color(resources, args[0])
        elif op == b'cs':
            fill = _cut_color(resources, args[0])
        elif op in (b'G', b'RG', b'K'):
            stroke = False
        elif op in (b'g', b'rg', b'k'):
            fill = False
        elif op == b'Tf':
            font = args[0]

        text_only = text_mode == 'created_only'
        created_text = created_scope or (font is not None and str(font).startswith('/AtlasText'))
        if op in stroke_ops and (stroke != cuts or text_only):
            # 's' closes the path before stroking; the path still ends here.
            op, args = b'n', []
        elif op in fill_ops and (fill != cuts or text_only):
            op, args = b'n', []
        elif op in both_ops:
            keep_stroke, keep_fill = stroke == cuts and not text_only, fill == cuts and not text_only
            if not keep_stroke and not keep_fill:
                op, args = b'n', []
            elif not keep_fill:
                op = b's' if op in (b'b', b'b*') else b'S'
            elif not keep_stroke:
                op = b'f*' if op in (b'B*', b'b*') else b'f'
        elif op == b'sh':
            if fill != cuts or text_only:
                continue
            used_shadings.add(args[0])
        elif op == b'Do':
            obj = xobjects[args[0]].get_object()
            if obj.get('/Subtype') == '/Form':
                # A fresh stream for every call also handles shared forms.
                form = DecodedStreamObject()
                form.update({key: value for key, value in obj.items() if key not in ('/Length', '/Filter', '/DecodeParms')})
                form.set_data(obj.get_data())
                _filter_content(form, writer, cuts, (stroke, fill, font), resources, depth + 1, text_mode, created_scope)
                name = NameObject('/AtlasForm' + str(len(used_xobjects)))
                while name in xobjects:
                    name = NameObject(str(name) + '_')
                xobjects[name] = writer._add_object(form)
                args = [name]
            elif cuts or text_only:
                continue
            else:
                obj.pop('/OC', None)
            used_xobjects.add(args[0])
        elif op == b'INLINE IMAGE' and (cuts or text_only):
            continue
        elif cuts and op in (b'BT', b'ET', b'Tf', b'Tj', b'TJ', b"'", b'"', b'Tm', b'Td', b'TD', b'T*', b'Tc', b'Tw', b'Tz', b'TL', b'Tr', b'Ts'):
            # CutContour is a path, not printed typography.
            continue
        elif op == b'Tf':
            used_fonts.add(args[0])
        if op in (b'Tj', b'TJ', b"'", b'"'):
            if (text_mode == 'without_created' and created_text) or (text_only and not created_text):
                continue
        operations.append((args, op))
    stream.operations = operations
    if owner.get('/Subtype') == '/Form':
        owner.set_data(stream.get_data())
    else:
        owner.replace_contents(stream)
        owner.pop('/Annots', None)
    for category, used in (('/XObject', used_xobjects), ('/Font', used_fonts), ('/Shading', used_shadings), ('/Properties', used_properties)):
        if category in resources:
            resources[NameObject(category)] = DictionaryObject({key: value for key, value in resources[category].items() if key in used})


def _separated_page(page, cuts, text_mode='all'):
    writer = PdfWriter()
    clone = writer.add_page(page)
    # Sheet placement uses the media canvas, irrespective of viewer rotation.
    # Render the same canvas and normalize an offset media box for PDFium.
    left, bottom = float(clone.mediabox.left), float(clone.mediabox.bottom)
    width, height = float(clone.mediabox.width), float(clone.mediabox.height)
    clone.rotation = 0
    if left or bottom:
        clone.add_transformation(Transformation().translate(-left, -bottom))
    for box in ('/MediaBox', '/CropBox', '/TrimBox', '/BleedBox', '/ArtBox'):
        clone[NameObject(box)] = RectangleObject([0, 0, width, height])
    _filter_content(clone, writer, cuts, text_mode=text_mode)
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    data = io.BytesIO()
    writer.write(data)
    return PdfReader(io.BytesIO(data.getvalue()))


def _raster_page(page, dpi):
    """Render a page whose cuts and optional vector text are already removed."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ValueError('Raster export needs pypdfium2. Install requirements.txt or untick Rasterize artwork.') from exc
    buffer = io.BytesIO()
    source_writer = PdfWriter()
    source_writer.add_page(page)
    source_writer.write(buffer)
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    if math.ceil(width * dpi / 72) * math.ceil(height * dpi / 72) > 40_000_000:
        raise ValueError('This PDF is too large at the selected DPI. Choose a lower resolution.')
    with pdfium.PdfDocument(buffer.getvalue()) as document:
        pdf_page = document[0]
        try:
            bitmap = pdf_page.render(scale=dpi / 72, rev_byteorder=True, force_bitmap_format=pdfium.raw.FPDFBitmap_BGR, draw_annots=False)
            try:
                pixels = bytes(bitmap.buffer)
                row_bytes = bitmap.width * 3
                pixels = b''.join(pixels[y * bitmap.stride:y * bitmap.stride + row_bytes] for y in range(bitmap.height))
                pixel_width, pixel_height = bitmap.width, bitmap.height
            finally:
                bitmap.close()
        finally:
            pdf_page.close()
    writer = PdfWriter()
    result = writer.add_blank_page(width=width, height=height)
    image = DecodedStreamObject()
    image.set_data(pixels)
    image.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                  NameObject('/Width'): NumberObject(pixel_width), NameObject('/Height'): NumberObject(pixel_height),
                  NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'): NumberObject(8)})
    image = image.flate_encode()
    result[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/AtlasRaster'): writer._add_object(image)})})
    content = DecodedStreamObject()
    content.set_data(f'q {width} 0 0 {height} 0 0 cm /AtlasRaster Do Q\n'.encode('ascii'))
    result[NameObject('/Contents')] = writer._add_object(content)
    result.compress_content_streams()
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    output = io.BytesIO()
    writer.write(output)
    return PdfReader(io.BytesIO(output.getvalue())).pages[0]


def prepare_export_parts(page, rasterize=False, dpi=300, rasterize_text=True):
    """Separate every label into artwork (including text) and vector cuts."""
    text_mode = 'without_created' if rasterize and not rasterize_text else 'all'
    artwork = _separated_page(page, False, text_mode).pages[0]
    cuts = _separated_page(page, True).pages[0]
    if rasterize:
        artwork = _raster_page(artwork, dpi)
        if not rasterize_text:
            text = _separated_page(page, False, 'created_only').pages[0]
            writer = PdfWriter()
            combined = writer.add_page(artwork)
            combined.merge_page(text)
            writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
            output = io.BytesIO()
            writer.write(output)
            artwork = PdfReader(io.BytesIO(output.getvalue())).pages[0]
    return {'artwork': artwork, 'cut': cuts}


def rasterize_artwork(page, dpi, rasterize_text=True):
    """Compatibility helper returning a label with raster art and vector cuts."""
    parts = prepare_export_parts(page, True, dpi, rasterize_text)
    writer = PdfWriter()
    result = writer.add_page(parts['artwork'])
    result.merge_page(parts['cut'])
    output = io.BytesIO()
    writer.write(output)
    return PdfReader(io.BytesIO(output.getvalue())).pages[0]


def export_layers(writer, page):
    """Register exactly two PDF optional-content groups, shared by all pages."""
    if '/OCProperties' not in writer._root_object:
        refs = [writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/OCG'),
                 NameObject('/Name'): TextStringObject(name)})) for name in ('artwork', 'cut')]
        writer._root_object[NameObject('/OCProperties')] = DictionaryObject({
            NameObject('/OCGs'): ArrayObject(refs),
            NameObject('/D'): DictionaryObject({NameObject('/BaseState'): NameObject('/ON'),
                NameObject('/Order'): ArrayObject(refs), NameObject('/ON'): ArrayObject(refs),
                NameObject('/OFF'): ArrayObject()}),
        })
        writer._root_object[NameObject('/PageMode')] = NameObject('/UseOC')
        if writer.pdf_header in ('%PDF-1.3', '%PDF-1.4'):
            writer.pdf_header = '%PDF-1.5'
    refs = writer._root_object['/OCProperties']['/OCGs']
    layers = {str(ref.get_object()['/Name']): ref for ref in refs}
    resources = page['/Resources']
    resources[NameObject('/Properties')] = DictionaryObject({
        NameObject('/ArtworkLayer'): layers['artwork'], NameObject('/CutLayer'): layers['cut']})
    return layers


def add_export_form(writer, xobjects, name, source_page, layer):
    form = DecodedStreamObject()
    form.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
        NameObject('/BBox'): source_page.trimbox.clone(writer),
        NameObject('/Resources'): source_page.get('/Resources', DictionaryObject()).clone(writer),
        NameObject('/OC'): layer})
    if '/Group' in source_page:
        form[NameObject('/Group')] = source_page['/Group'].clone(writer)
    content = source_page.get_contents()
    form.set_data(content.get_data() if content is not None else b'')
    xobjects[name] = writer._add_object(form)


def export_label_pdf(page, rasterize, dpi, rasterize_text=True):
    parts = prepare_export_parts(page, rasterize, dpi, rasterize_text)
    writer = PdfWriter()
    result = writer.add_blank_page(width=float(page.mediabox.width), height=float(page.mediabox.height))
    xobjects = DictionaryObject()
    result[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): xobjects})
    layers = export_layers(writer, result)
    content = ContentStream(None, writer)
    for layer, property_name in (('artwork', '/ArtworkLayer'), ('cut', '/CutLayer')):
        name = NameObject('/Label' + layer)
        add_export_form(writer, xobjects, name, parts[layer], layers[layer])
        content.operations.extend([([NameObject('/OC'), NameObject(property_name)], b'BDC'),
                                   ([], b'q'), ([name], b'Do'), ([], b'Q'), ([], b'EMC')])
    result.replace_contents(content)
    result.compress_content_streams()
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
