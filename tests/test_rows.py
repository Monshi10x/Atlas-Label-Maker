import io
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from atlas_label_maker import AppState,AppPaths,AppError,PdfReader
from label_designer import create_label

class RowTests(unittest.TestCase):
    def test_rows_regenerate_independently_and_preserve_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);state=AppState(AppPaths.create(root))
            original,_=create_label({'title':'ORIGINAL','specification':'3x12 DLC'})
            first=state.store_label_upload('first.pdf',original)
            second=state.store_label_upload('second.pdf',original)
            self.assertTrue(first['editable'])
            self.assertEqual(first['title'],'ORIGINAL')
            rows=[{'source_token':first['token'],'editable':True,'title':'FIRST EDIT','specification':'6x15 DLC'},
                  {'source_token':second['token'],'editable':True,'title':'SECOND EDIT','specification':'8x25 DLC'}]
            opts={'template_id':'1'*32,'generate_combined':True,'combined_name':'Tool Label - FIRST EDIT 6x15 DLC','output_folder':str(root/'out'),'label_rows':rows}
            result=state.generate_rows(opts)
            pages=PdfReader(result['created'][0]).pages
            self.assertEqual(len(pages),2)
            self.assertIn('FIRST EDIT',pages[0].extract_text());self.assertNotIn('SECOND EDIT',pages[0].extract_text())
            self.assertIn('SECOND EDIT',pages[1].extract_text());self.assertNotIn('FIRST EDIT',pages[1].extract_text())
            self.assertEqual(len(state.uploads),2)
            self.assertEqual(Path(state.get_upload(first['token'])['path']).read_bytes(),original)
            result=state.generate_rows({**opts,'combine_one_page':True})
            page=PdfReader(result['created'][0]).pages[0]
            self.assertIn('FIRST EDIT',page.extract_text());self.assertIn('SECOND EDIT',page.extract_text())
            self.assertEqual(str(page['/Resources']['/ColorSpace']['/ATCutContour'][1]),'/CutContour')
            existing=set((root/'out').iterdir())
            with self.assertRaises(AppError):state.generate_rows({**opts,'label_rows':[rows[0],{**rows[1],'title':'A'*100}]})
            self.assertEqual(set((root/'out').iterdir()),existing)
            self.assertEqual(len(state.uploads),2)

    def test_font_and_blank_template(self):
        root=Path(__file__).resolve().parents[1]/'app'
        blank=PdfReader(root/'tool_label_templates/Atlas Tool Label.pdf').pages[0]
        self.assertEqual(blank.extract_text().count('Lorem Ipsum'),2)
        data,_=create_label({'title':'Compression Spiral','specification':'Ø6 × 15 DLC'})
        page=PdfReader(io.BytesIO(data)).pages[0]
        font=page['/Resources']['/Font']['/AtlasText']['/DescendantFonts'][0].get_object()
        self.assertEqual(font['/FontDescriptor']['/FontFile2'].get_data(),(root/'label_assets/Poppins-Regular.ttf').read_bytes())

if __name__=='__main__':unittest.main()
