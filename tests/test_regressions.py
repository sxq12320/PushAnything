import base64
import concurrent.futures
import io
import json
import os
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

import conftest_support as support
from PIL import Image
import backend
import jobs
import image_store
import mdconvert
import storage


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.api = backend.Api()

    def save(self, title, body, rel='', folder=''):
        return self.api.save_article(rel, title, '作者', '', '', body, 'blue', folder, True)

    def test_same_title_preserves_both_drafts(self):
        first = self.save('同名稿', '第一篇')
        second = self.save('同名稿', '第二篇')
        self.assertNotEqual(first['rel'], second['rel'])
        self.assertEqual(self.api.load_article(first['rel'])['md'], '第一篇')
        self.assertEqual(self.api.load_article(second['rel'])['md'], '第二篇')

    def test_concurrent_new_drafts_get_unique_names(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(lambda n: self.save('并发稿', str(n)), range(12)))
        self.assertEqual(len({value['rel'] for value in values}), 12)

    def test_reserved_names_and_traversal_stay_inside_drafts(self):
        for rel in ['../逃逸', '..\\逃逸', 'CON', 'NUL.txt', 'a/../../bad']:
            path, _ = backend._paths(rel)
            self.assertEqual(os.path.commonpath([path, backend.DRAFTS_DIR]), backend.DRAFTS_DIR)
            self.assertNotIn('..', Path(path).parts)
        self.assertEqual(backend._slug('CON'), '_CON')

    def test_move_collision_keeps_metadata_and_images(self):
        raw = io.BytesIO(); Image.new('RGB', (100, 70), 'red').save(raw, 'PNG')
        first = self.save('移动同名', '原文', folder='移出')
        image = self.api.save_pasted_image(first['rel'], 'data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode())
        body = '原文\n![图](<' + image['src'] + '>)'
        self.save('移动同名', body, rel=first['rel'])
        second = self.save('移动同名', '目标旧稿', folder='移入')
        moved = self.api.move_article(first['rel'], '移入')
        self.assertNotEqual(moved['rel'], second['rel'])
        self.assertEqual(self.api.load_article(second['rel'])['md'], '目标旧稿')
        article = self.api.load_article(moved['rel'])
        self.assertIn('原文', article['md'])
        html = self.api.preview(article['md'], 'wechat', 'blue', moved['rel'])['html']
        self.assertIn('data:image/', html)
        self.assertNotIn('移入/assets', [f['name'] for f in self.api.list_folders()])

    def test_delete_and_restore_retains_latest_content(self):
        article = self.save('可恢复稿', '最新内容')
        deleted = self.api.delete_article(article['rel'])
        self.assertIsNone(self.api.load_article(article['rel']))
        restored = self.api.restore_article(deleted['token'])
        self.assertEqual(self.api.load_article(restored['rel'])['md'], '最新内容')
        self.assertNotIn('.trash', [f['name'] for f in self.api.list_folders()])

    def test_folder_delete_pairs_same_name_files(self):
        first = self.save('文件夹重名', '根目录')
        second = self.save('文件夹重名', '子目录', folder='待删除')
        self.api.delete_folder('待删除')
        self.assertEqual(self.api.load_article(first['rel'])['md'], '根目录')
        matching = [a for a in self.api.list_articles() if a['title'] == '文件夹重名']
        self.assertEqual(len(matching), 2)
        self.assertEqual({self.api.load_article(a['rel'])['md'] for a in matching}, {'根目录', '子目录'})

    def test_custom_template_keeps_image_after_folder_removal(self):
        article = self.save('模板来源', '模板', folder='模板原稿')
        buffer = io.BytesIO(); Image.new('RGB', (30, 20), 'green').save(buffer, 'PNG')
        imported = self.api.save_pasted_image(article['rel'], 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode())
        result = self.api.save_template('含图片模板', '![图](<' + imported['src'] + '>)', 'green', article['rel'])
        self.api.delete_folder('模板原稿')
        rendered = self.api.preview(result['template']['md'], 'wechat', 'green')['html']
        self.assertIn('data:image/', rendered)

    def test_recovery_clear_does_not_remove_newer_revision(self):
        self.api.save_recovery({'session': 's', 'revision': 4, 'md': '新内容'})
        self.api.clear_recovery('s', 3)
        self.assertIsNotNone(self.api.get_recovery())
        self.api.clear_recovery('s', 4)
        self.assertIsNone(self.api.get_recovery())

    def test_preview_never_downloads_remote_images(self):
        with patch.object(mdconvert, 'download_image', side_effect=AssertionError('network')):
            result = self.api.preview('![远程](https://example.com/a.png)', 'wechat', 'blue')
        self.assertIn('https://example.com/a.png', result['html'])

    def test_existing_draft_content_survives_failed_atomic_replace(self):
        article = self.save('落盘失败', '旧内容')
        with patch.object(storage.os, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.save('落盘失败', '新内容', rel=article['rel'])
        self.assertEqual(self.api.load_article(article['rel'])['md'], '旧内容')


class ImageTests(unittest.TestCase):
    def test_resize_original_and_deduplication(self):
        raw = io.BytesIO(); Image.new('RGB', (3600, 2000), 'blue').save(raw, 'JPEG')
        result = image_store.import_bytes(raw.getvalue(), str(support.DATA / 'images'))
        self.assertEqual(result['width'], 2560)
        self.assertTrue(Path(result['original_path']).is_file())
        self.assertEqual(Path(result['original_path']).read_bytes(), raw.getvalue())
        self.assertEqual(image_store.import_bytes(raw.getvalue(), str(support.DATA / 'images'))['src'], result['src'])

    def test_exif_rotation(self):
        raw = io.BytesIO(); image = Image.new('RGB', (100, 50), 'blue')
        exif = image.getexif(); exif[274] = 6; image.save(raw, 'JPEG', exif=exif)
        result = image_store.import_bytes(raw.getvalue(), str(support.DATA / 'images'))
        self.assertEqual((result['width'], result['height']), (50, 100))

    def test_transparency_and_animation_are_preserved(self):
        raw = io.BytesIO(); Image.new('RGBA', (20, 20), (1, 2, 3, 0)).save(raw, 'PNG')
        result = image_store.import_bytes(raw.getvalue(), str(support.DATA / 'images'))
        self.assertTrue(result['src'].endswith('.png'))
        with Image.open(result['path']) as image:
            self.assertEqual(image.getpixel((0, 0))[3], 0)
        raw = io.BytesIO(); image = Image.new('RGB', (20, 20), 'red')
        image.save(raw, 'GIF', save_all=True, append_images=[Image.new('RGB', (20, 20), 'blue')], duration=100, loop=0)
        result = image_store.import_bytes(raw.getvalue(), str(support.DATA / 'images'))
        self.assertTrue(result['animated'])
        self.assertEqual(Path(result['path']).read_bytes(), raw.getvalue())


class QueueTests(unittest.TestCase):
    def test_failure_partial_attention_and_safe_retry(self):
        import runner
        history = str(support.DATA / 'test-history.json')
        with patch.object(runner, 'run_job', return_value={'wechat': {'ok': True}, 'zhihu': {'ok': False, 'err': 'failed'}}):
            queue = jobs.JobQueue(history)
            job = queue.submit('article', {'title': '队列稿', 'md': 'text', 'platforms': {'wechat': True, 'zhihu': True}})
            self.assertTrue(job.completed.wait(5))
            self.assertEqual(job.status, 'partial')
        with patch.object(runner, 'run_job', return_value={'zhihu': {'ok': True}}):
            retry = queue.retry(job.id)
            self.assertTrue(retry.completed.wait(5))
            self.assertEqual(retry.payload['platforms'], {'zhihu': True})
            self.assertEqual(retry.status, 'done')
        restarted = jobs.JobQueue(history)
        self.assertEqual(restarted.detail(job.id)['status'], 'partial')
        self.assertNotIn('_payload', restarted.detail(job.id))
        for result, expected in [({'wechat': {'ok': False}}, 'error'), ({'zhihu': {'ok': True, 'needs_attention': True}}, 'attention')]:
            with patch.object(runner, 'run_job', return_value=result):
                item = queue.submit('article', {'title': '状态稿'})
                self.assertTrue(item.completed.wait(5))
                self.assertEqual(item.status, expected)

    def test_cancel_queued_and_concurrent_history_reads(self):
        import runner
        gate = threading.Event()
        entered = threading.Event()
        def wait(job):
            entered.set(); gate.wait(5); return {'wechat': {'ok': True}}
        with patch.object(runner, 'run_job', side_effect=wait):
            queue = jobs.JobQueue(str(support.DATA / 'cancel-history.json'))
            first = queue.submit('article', {'title': '执行中'})
            self.assertTrue(entered.wait(3))
            pending = queue.submit('article', {'title': '待执行'})
            self.assertTrue(queue.cancel(pending.id))
            self.assertEqual(queue.detail(pending.id)['status'], 'cancelled')
            self.assertFalse(queue.cancel(first.id))
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                self.assertTrue(all(pool.map(lambda _: len(queue.recent()) == 2, range(50))))
            gate.set(); self.assertTrue(first.completed.wait(5))


if __name__ == '__main__':
    unittest.main(verbosity=2)
