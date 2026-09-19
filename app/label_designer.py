"""Fixed artwork, editable vector text. Uses only vendored Python packages."""
import io
import re
from pathlib import Path
from fontTools.ttLib import TTFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, ContentStream, DecodedStreamObject,
    DictionaryObject, FloatObject, NameObject, NumberObject, TextStringObject)

ASSETS = Path(__file__).parent / 'label_assets'

def dictionary(**values):
    return DictionaryObject({NameObject('/' + k): v for k, v in values.items()})

def stream(writer, data):
    obj = DecodedStreamObject(); obj.set_data(data)
    return writer._add_object(obj.flate_encode())

def read_font(data):
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('Font must be smaller than 10 MB.')
    try:
        font = TTFont(io.BytesIO(data))
        if 'glyf' not in font or 'fvar' in font:
            raise ValueError('Use a static TrueType (.ttf) font, such as Poppins-Regular.ttf.')
        if 'OS/2' in font and font['OS/2'].fsType & (2 | 512):
            raise ValueError('This font does not permit outline embedding. Choose an embeddable font.')
        if not font.getBestCmap():
            raise ValueError('This font has no supported character map.')
        font['hmtx']; font['head']; font['hhea']
        return font
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Invalid font. Upload a static TrueType (.ttf) file.') from exc

def font_resource(writer, texts, font_data):
    if not font_data:
        font_data = (ASSETS / 'Poppins-Regular.ttf').read_bytes()
    font = read_font(font_data)
    font_name = NameObject('/' + re.sub(r'[^A-Za-z0-9_-]', '', font['name'].getDebugName(6) or 'AtlasCustom'))
    cmap = font.getBestCmap(); chars = sorted(set(''.join(texts)))
    missing = [c for c in chars if ord(c) not in cmap]
    if missing: raise ValueError('Font is missing characters: ' + ' '.join(missing))
    units = font['head'].unitsPerEm
    scale = lambda n: round(n * 1000 / units)
    ids = {c: i + 1 for i, c in enumerate(chars)}
    widths = {c: scale(font['hmtx'][cmap[ord(c)]][0]) for c in chars}
    gids = b'\x00\x00' + b''.join(font.getGlyphID(cmap[ord(c)]).to_bytes(2,'big') for c in chars)
    descriptor = dictionary(Type=NameObject('/FontDescriptor'), FontName=font_name,
        Flags=NumberObject(32), FontBBox=ArrayObject([NumberObject(scale(getattr(font['head'], k))) for k in ('xMin','yMin','xMax','yMax')]),
        ItalicAngle=NumberObject(0), Ascent=NumberObject(scale(font['hhea'].ascent)),
        Descent=NumberObject(scale(font['hhea'].descent)), CapHeight=NumberObject(scale(getattr(font.get('OS/2'), 'sCapHeight',font['hhea'].ascent))), StemV=NumberObject(80))
    file_obj=DecodedStreamObject(); file_obj.set_data(font_data); file_obj[NameObject('/Length1')]=NumberObject(len(font_data))
    descriptor[NameObject('/FontFile2')] = writer._add_object(file_obj.flate_encode())
    cid = dictionary(Type=NameObject('/Font'), Subtype=NameObject('/CIDFontType2'), BaseFont=font_name,
        CIDSystemInfo=dictionary(Registry=TextStringObject('Adobe'),Ordering=TextStringObject('Identity'),Supplement=NumberObject(0)),
        FontDescriptor=writer._add_object(descriptor), CIDToGIDMap=stream(writer,gids),
        W=ArrayObject([NumberObject(1), ArrayObject([NumberObject(widths[c]) for c in chars])]))
    mapping = '\n'.join(str(len(chars[i:i+100])) + ' beginbfchar\n' + '\n'.join(f'<{ids[c]:04x}> <{c.encode("utf-16-be").hex()}>' for c in chars[i:i+100]) + '\nendbfchar' for i in range(0,len(chars),100))
    unicode_map = f'/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /AtlasUnicode def /CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange \n{mapping}\n endcmap CMapName currentdict /CMap defineresource pop end end'.encode('ascii')
    resource=writer._add_object(dictionary(Type=NameObject('/Font'), Subtype=NameObject('/Type0'),BaseFont=font_name,
        Encoding=NameObject('/Identity-H'), DescendantFonts=ArrayObject([writer._add_object(cid)]), ToUnicode=stream(writer,unicode_map)))
    return resource, [(''.join(f'{ids[c]:04x}' for c in text),sum(widths[c] for c in text)) for text in texts]

def create_label(payload, font_data=None, source_path=None):
    texts=[]
    for key in ('title','specification'):
        value=payload.get(key,'')
        if not isinstance(value,str): raise ValueError('Label text must be text.')
        value=value.strip()
        if not value or len(value)>100 or any(ord(c)<32 for c in value):
            raise ValueError('Each line needs 1–100 characters, with no line breaks.')
        texts.append(value)
    reader=PdfReader(source_path or ASSETS.parent/'tool_label_templates'/'Atlas Tool Label.pdf'); writer=PdfWriter(); page=writer.add_page(reader.pages[0])
    # Remove original text operators, rather than hiding old product information.
    content=ContentStream(page.get_contents(),writer)
    content.operations=[(args,op) for args,op in content.operations if op not in (b'Tj',b'TJ',b"'",b'"')]
    page.replace_contents(content)
    resource, lines=font_resource(writer,texts,font_data)
    page['/Resources']['/Font'][NameObject('/AtlasText')]=resource
    commands=[]; sizes=[]
    for (encoded,width),baseline in zip(lines,(25.542,13.3013)):
        size=min(5.0, 58.0*1000/max(width,1))
        if size < 3.0: raise ValueError('Text is too long to remain readable. Shorten the line (minimum 3 pt).')
        sizes.append(round(size,2))
        commands.append(f'q 0 0 0 1 k BT /AtlasText {size:.5f} Tf 0 Tc 0 Tw 100 Tz 0 Ts 0 Tr 1 0 0 1 84.1699 {baseline} Tm <{encoded}> Tj ET Q')
    extra=DecodedStreamObject();extra.set_data(('\n'.join(commands)).encode('ascii'))
    page[NameObject('/Contents')]=ArrayObject([page.raw_get('/Contents'),writer._add_object(extra)])
    out=io.BytesIO();writer.write(out)
    return out.getvalue(),sizes
