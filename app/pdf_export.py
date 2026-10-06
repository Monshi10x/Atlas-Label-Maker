"""Raster artwork independently of vector CutContour paths."""
import io
import math

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import (
    ArrayObject, ContentStream, DecodedStreamObject, DictionaryObject,
    NameObject, NumberObject, RectangleObject,
)


def export_options(payload):
    rasterize = payload.get('rasterize', True)
    if not isinstance(rasterize, bool):
        raise ValueError('Rasterize must be enabled or disabled.')
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


def _filter_content(owner, writer, cuts, inherited=(False, False), parent_resources=None, depth=0):
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
    xobjects = DictionaryObject(resources.get('/XObject', {}).get_object()) if '/XObject' in resources else DictionaryObject()
    resources[NameObject('/XObject')] = xobjects
    stream = ContentStream(owner if owner.get('/Subtype') == '/Form' else owner.get_contents(), writer)
    stroke, fill = inherited
    stack, operations = [], []
    used_xobjects, used_fonts, used_shadings = set(), set(), set()
    stroke_ops = {b'S', b's'}
    fill_ops = {b'f', b'F', b'f*'}
    both_ops = {b'B', b'B*', b'b', b'b*'}
    for args, op in stream.operations:
        if op == b'q':
            stack.append((stroke, fill))
        elif op == b'Q' and stack:
            stroke, fill = stack.pop()
        elif op == b'CS':
            stroke = _cut_color(resources, args[0])
        elif op == b'cs':
            fill = _cut_color(resources, args[0])
        elif op in (b'G', b'RG', b'K'):
            stroke = False
        elif op in (b'g', b'rg', b'k'):
            fill = False

        if op in stroke_ops and stroke != cuts:
            # 's' closes the path before stroking; the path still ends here.
            op, args = b'n', []
        elif op in fill_ops and fill != cuts:
            op, args = b'n', []
        elif op in both_ops:
            keep_stroke, keep_fill = stroke == cuts, fill == cuts
            if not keep_stroke and not keep_fill:
                op, args = b'n', []
            elif not keep_fill:
                op = b's' if op in (b'b', b'b*') else b'S'
            elif not keep_stroke:
                op = b'f*' if op in (b'B*', b'b*') else b'f'
        elif op == b'sh':
            if fill != cuts:
                continue
            used_shadings.add(args[0])
        elif op == b'Do':
            obj = xobjects[args[0]].get_object()
            if obj.get('/Subtype') == '/Form':
                # A fresh stream for every call also handles shared forms.
                form = DecodedStreamObject()
                form.update({key: value for key, value in obj.items() if key not in ('/Length', '/Filter', '/DecodeParms')})
                form.set_data(obj.get_data())
                _filter_content(form, writer, cuts, (stroke, fill), resources, depth + 1)
                name = NameObject('/AtlasForm' + str(len(used_xobjects)))
                while name in xobjects:
                    name = NameObject(str(name) + '_')
                xobjects[name] = writer._add_object(form)
                args = [name]
            elif cuts:
                continue
            used_xobjects.add(args[0])
        elif op == b'INLINE IMAGE' and cuts:
            continue
        elif cuts and op in (b'BT', b'ET', b'Tf', b'Tj', b'TJ', b"'", b'"', b'Tm', b'Td', b'TD', b'T*', b'Tc', b'Tw', b'Tz', b'TL', b'Tr', b'Ts'):
            # CutContour is a path, not printed typography.
            continue
        elif op == b'Tf':
            used_fonts.add(args[0])
        operations.append((args, op))
    stream.operations = operations
    if owner.get('/Subtype') == '/Form':
        owner.set_data(stream.get_data())
    else:
        owner.replace_contents(stream)
        owner.pop('/Annots', None)
    for category, used in (('/XObject', used_xobjects), ('/Font', used_fonts), ('/Shading', used_shadings)):
        if category in resources:
            resources[NameObject(category)] = DictionaryObject({key: value for key, value in resources[category].items() if key in used})


def _separated_page(page, cuts):
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
    _filter_content(clone, writer, cuts)
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    data = io.BytesIO()
    writer.write(data)
    return PdfReader(io.BytesIO(data.getvalue()))


def rasterize_artwork(page, dpi):
    """Return one reusable raster label page with its vector cuts overlaid."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ValueError('Raster export needs pypdfium2. Install requirements.txt or untick Rasterize artwork.') from exc
    artwork = _separated_page(page, False)
    cuts = _separated_page(page, True)
    buffer = io.BytesIO()
    source_writer = PdfWriter()
    source_writer.add_page(artwork.pages[0])
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
    cut_page = cuts.pages[0]
    result.merge_page(cut_page)
    result.compress_content_streams()
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    output = io.BytesIO()
    writer.write(output)
    return PdfReader(io.BytesIO(output.getvalue())).pages[0]
