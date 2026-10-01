import re
import unittest
from unittest.mock import patch

import conftest_support
import backend
import math_render
import mdconvert
import wechat_push
import browser as browser_tools
from PIL import Image
from playwright.sync_api import sync_playwright


class MathTests(unittest.TestCase):
    def test_short_and_long_keep_glyph_size_and_raster_density(self):
        short = math_render.render_formula('x=x+x', True)
        long = math_render.render_formula('x=' + '+'.join(['x'] * 45), True)
        self.assertGreater(long.width, short.width * 10)
        self.assertEqual(short.height, long.height)
        for result in (short, long):
            with Image.open(result.path) as bitmap:
                self.assertEqual(bitmap.width / result.width, 3)
                self.assertEqual(bitmap.height / result.height, 3)
                ink = bitmap.getchannel('A').crop((9, 0, 35, bitmap.height)).getbbox()
                self.assertIsNotNone(ink)
                if result is short:
                    short_ink_height = ink[3] - ink[1]
                else:
                    self.assertLessEqual(abs(ink[3] - ink[1] - short_ink_height), 1)

    def test_export_wraps_without_reducing_font(self):
        for display in (True, False):
            short = math_render.render_formula('x=x+x', display, max_width=320)
            long = math_render.render_formula('x=' + '+'.join(['x'] * 45), display, max_width=320)
            self.assertLessEqual(long.width, 320)
            self.assertGreater(long.height, short.height * 2)
            with Image.open(short.path) as a, Image.open(long.path) as b:
                self.assertEqual(a.info['formula_font_px'], b.info['formula_font_px'])

    def test_aligned_matrix_and_fraction_are_available_offline(self):
        with patch('requests.get', side_effect=AssertionError('Formula should stay offline')):
            for source in [r'\begin{aligned}a&=b+c\\d&=e+f\end{aligned}',
                           r'\begin{pmatrix}a&b\\c&d\end{pmatrix}', r'\frac{x_i^2}{\sqrt{n}}']:
                image = math_render.render_formula(source, True, max_width=320)
                self.assertGreater(image.height, 20)

    def test_invalid_source_is_visible_in_preview_and_blocks_export(self):
        source = '前面的正文\n\n$$\\frac{$$\n\n后面的正文'
        preview = backend.Api().preview(source, 'wechat', 'wild')['html']
        self.assertIn('公式未完成', preview)
        self.assertIn('后面的正文', preview)
        with self.assertRaises(math_render.MathRenderError):
            mdconvert.richtext_html(source)

    def test_code_fences_and_escaped_dollars_are_preserved(self):
        source = '```latex\n$x$\n```\n\n~~~latex\n$$y$$\n~~~\n\n``$z$``\n\n\\$literal\n\n$\\text{cost \\$5}$'
        cleaned, formulas = mdconvert.extract_math(source)
        self.assertEqual(list(formulas.values()), [(r'\text{cost \$5}', False)])
        self.assertIn('$$y$$', cleaned)
        self.assertIn('``$z$``', cleaned)

    def test_wechat_upload_retains_formula_dimensions_and_alignment(self):
        html = mdconvert.richtext_html('正文 $\\frac{1}{x}$。\n\n$$x=x+x$$')
        with patch.object(wechat_push, '_upload', return_value=('mock-id', 'https://example.invalid/image.png')):
            uploaded = wechat_push._inline_images({}, 'mock-token', html, lambda message: None)
        before = re.findall(r'<img[^>]+>', html)
        after = re.findall(r'<img[^>]+>', uploaded)
        self.assertEqual(len(before), 2)
        self.assertEqual(len(after), 2)
        for original, result in zip(before, after):
            for attribute in ['width', 'height', 'style']:
                self.assertEqual(re.search(attribute + r'="([^"]*)"', original)[1],
                                 re.search(attribute + r'="([^"]*)"', result)[1])
        self.assertIn('vertical-align:-', uploaded)

    def test_segment_sizes_survive_image_pipeline(self):
        result = mdconvert.make_segments('$$x=x+x$$', '', backend.FONT_R, backend.FONT_B)
        image = next(item for item in result if item['type'] == 'image')
        self.assertTrue(image['formula'])
        with Image.open(image['path']) as bitmap:
            self.assertLessEqual(abs(image['width'] - bitmap.width / 3), .5)
            self.assertLessEqual(abs(image['height'] - bitmap.height / 3), .5)

    def test_atomic_expression_is_not_silently_shrunk_for_export(self):
        source = r'\frac{' + 'x' * 120 + '}{y}'
        with self.assertRaises(math_render.MathRenderError):
            math_render.render_formula(source, True, max_width=320)
        preview = math_render.render_formula(source, True)
        self.assertGreater(preview.width, 320)

    def test_formula_upload_sizes_the_body_image_not_the_title(self):
        image = math_render.render_formula('x=x+x', True, max_width=320)
        with sync_playwright() as pw:
            engine = pw.chromium.launch(channel='msedge', headless=True)
            try:
                page = engine.new_page()
                page.set_content('''<div contenteditable="true" id="title">标题</div>
                  <div contenteditable="true" id="body"></div><input type="file" accept="image/*">
                  <script>document.querySelector('input').onchange = event => {
                    const reader = new FileReader(); reader.onload = () => {
                      const image = document.createElement('img'); image.src = reader.result;
                      document.getElementById('body').append(image);
                    }; reader.readAsDataURL(event.target.files[0]);
                  };</script>''')
                body = page.locator('#body')
                body.evaluate('(node)=>node.style.minHeight="30px"')
                browser_tools.fill_segments(page, body, [{'type':'image', 'path':image.path,
                    'formula':True, 'width':round(image.width), 'height':round(image.height)}], lambda _:None, [])
                dimensions = body.locator('img').evaluate('(node)=>({width:node.width,height:node.height,naturalWidth:node.naturalWidth})')
                self.assertEqual(dimensions['width'], round(image.width))
                self.assertEqual(dimensions['height'], round(image.height))
                self.assertEqual(page.locator('#title img').count(), 0)
            finally:
                engine.close()


if __name__ == '__main__':
    unittest.main()
