import io
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from atlas_label_maker import AppState, AppPaths, AppError, PdfReader, PdfWriter
from label_designer import create_label

class DesignerTests(unittest.TestCase):
    def test_text_and_dimensions(self):
        data,sizes=create_label({'title':'Aluminium Up-Spiral','specification':'6 × 15 DLC'})
        page=PdfReader(io.BytesIO(data)).pages[0]
        self.assertIn('Aluminium Up-Spiral',page.extract_text())
        self.assertNotIn('Compression Spiral',page.extract_text())
        self.assertAlmostEqual(float(page.mediabox.width),55*72/25.4,places=3)
        self.assertEqual(sizes,[5,5])
    def test_bad_text(self):
        for text in ('','A'*100,'bad\nline','\U0010FFFF'):
            with self.assertRaises(ValueError):create_label({'title':text,'specification':'6 mm'})
    def test_workflows(self):
        with tempfile.TemporaryDirectory() as folder:
            state=AppState(AppPaths.create(Path(folder)))
            a=state.designer_add({'title':'Compression Spiral','specification':'6x22 DLC'})['upload']
            b=state.designer_add({'title':'Up-Spiral','specification':'8x25 DLC'})['upload']
            for mixed in (False,True):
                result=state.generate({'template_id':'1'*32,'label_tokens':[a['token'],b['token']],
                    'combine_one_page':mixed,'generate_combined':True,'generate_individual':True,
                    'output_folder':str(Path(folder)/'out'),'combined_name':'test'})
                self.assertEqual(result['page_count'],1 if mixed else 2)
                for name in result['created']:
                    for page in PdfReader(name).pages:
                        cs=page['/Resources']['/ColorSpace']['/ATCutContour']
                        self.assertEqual(str(cs[1]),'/CutContour')
                        self.assertIn(b'1 w',page.get_contents().get_data())
            writer=PdfWriter();writer.add_blank_page(width=35*72/25.4,height=35*72/25.4)
            buf=io.BytesIO();writer.write(buf)
            collet=state.store_label_upload('Collet.pdf',buf.getvalue())
            state.generate({'template_id':'2'*32,'label_tokens':[collet['token']], 'generate_combined':True,
                'output_folder':str(Path(folder)/'out'),'combined_name':'collet'})
            with self.assertRaises(AppError):
                state.generate({'template_id':'2'*32,'label_tokens':[a['token']]})
            restored=AppState(AppPaths.create(Path(folder)))
            self.assertEqual(restored.designer_info()['draft']['title'],'Up-Spiral')
            backup=state.export_library();restored.import_library(backup)
            self.assertEqual(len(restored.list_templates()),2)

if __name__=='__main__':unittest.main()
