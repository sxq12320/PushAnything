import http.client
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import conftest_support as support
import api_server
import backend
import jobs
import storage


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = api_server.start(0, token='test-only-token')
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); api_server._server = None

    def call(self, method, url, data=None, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        body = raw if raw is not None else json.dumps(data) if data is not None else None
        request_headers = {'Content-Type': 'application/json', 'X-Token': 'test-only-token'}
        request_headers.update(headers or {})
        connection.request(method, url, body, request_headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_auth_and_foreign_origin(self):
        self.assertEqual(self.call('GET', '/api/tasks', headers={'X-Token': 'incorrect'})[0], 401)
        self.assertEqual(self.call('POST', '/api/article', {'title': '稿'}, headers={'Origin': 'https://foreign.example'})[0], 401)

    def test_malformed_json_and_invalid_payloads_are_400(self):
        for raw in ['[]', '{', 'null', '123']:
            self.assertEqual(self.call('POST', '/api/article', raw=raw)[0], 400)
        for payload in [
            {'title': 123, 'md': 'text', 'platforms': ['wechat']},
            {'title': '标题', 'md': 'text', 'platforms': 'wechat'},
            {'title': '标题', 'md': 'text', 'platforms': {'wechat': False}},
            {'title': '标题', 'md': 'text', 'platforms': {'unknown': True}},
            {'title': '标题', 'md': '', 'platforms': ['wechat']},
        ]:
            self.assertEqual(self.call('POST', '/api/article', payload)[0], 400)

    def test_history_detail_works_after_restart(self):
        entry = {'id': 'historical', 'kind': 'article', 'status': 'done', 'source': 'ui',
                 'logs': [], 'results': {'wechat': {'ok': True}}, 'title': '旧任务',
                 'platforms': ['wechat'], 'created': 1, 'finished': 2}
        jobs.queue._hist[entry['id']] = entry
        status, result = self.call('GET', '/api/tasks/historical')
        self.assertEqual(status, 200)
        self.assertEqual(result['task']['title'], '旧任务')
        self.assertNotIn('_payload', result['task'])

    def test_mobile_article_keeps_folder_base_and_hides_trash(self):
        api = backend.Api()
        article = api.save_article('', '手机路径', '', '', '', '图片正文', 'wild', '手机目录', True)
        deleted = api.save_article('', '已删除稿', '', '', '', 'secret', 'blue', '', True)
        api.delete_article(deleted['rel'])
        status, result = self.call('GET', '/api/articles')
        self.assertEqual(status, 200)
        item = next(item for item in result['articles'] if item['rel'] == article['rel'])
        self.assertTrue(item['base_dir'].endswith('手机目录'))
        self.assertFalse(any(item['title'] == '已删除稿' for item in result['articles']))


class MigrationTests(unittest.TestCase):
    def load_paths(self, root):
        spec = importlib.util.spec_from_file_location('migration_paths', support.ROOT / 'app/paths.py')
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(root / 'PushAnything.exe')), patch.object(sys, '_MEIPASS', str(root / 'bundle'), create=True):
            spec.loader.exec_module(module)
        return module

    def test_migration_keeps_source_rebases_paths_and_waits_until_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'root'; root.mkdir()
            source = Path(directory) / 'source'; (source / 'drafts').mkdir(parents=True)
            target = Path(directory) / 'destination'
            body = '![图](<' + (source / 'drafts/assets/a.png').as_posix() + '>)'
            (source / 'drafts/a.md').write_text(body, encoding='utf-8')
            storage.atomic_json(source / 'templates.json', [{'md': body}])
            storage.atomic_json(root / 'config.json', {'data_dir': str(source), 'pending_data_dir': str(target)})
            module = self.load_paths(root)
            self.assertEqual(module.DATA_DIR, str(target))
            self.assertEqual((source / 'drafts/a.md').read_text(encoding='utf-8'), body)
            self.assertIn(target.as_posix(), (target / 'drafts/a.md').read_text(encoding='utf-8'))
            config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
            self.assertNotIn('pending_data_dir', config)

    def test_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'root'; root.mkdir()
            source = Path(directory) / 'source'; (source / 'drafts').mkdir(parents=True)
            target = Path(directory) / 'target'; (target / 'drafts').mkdir(parents=True)
            (target / 'drafts/original.md').write_text('原始数据', encoding='utf-8')
            storage.atomic_json(root / 'config.json', {'data_dir': str(source), 'pending_data_dir': str(target)})
            module = self.load_paths(root)
            self.assertEqual(module.DATA_DIR, str(source))
            self.assertTrue(module.STARTUP_WARNING)
            self.assertEqual((target / 'drafts/original.md').read_text(encoding='utf-8'), '原始数据')

    def test_copy_failure_leaves_source_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'root'; root.mkdir()
            source = Path(directory) / 'source'; (source / 'drafts').mkdir(parents=True)
            (source / 'drafts/a.md').write_text('保留内容', encoding='utf-8')
            storage.atomic_json(root / 'config.json', {'data_dir': str(source), 'pending_data_dir': str(Path(directory) / 'target')})
            with patch('shutil.copytree', side_effect=OSError('copy failed')):
                module = self.load_paths(root)
            self.assertEqual(module.DATA_DIR, str(source))
            self.assertEqual((source / 'drafts/a.md').read_text(encoding='utf-8'), '保留内容')


if __name__ == '__main__':
    unittest.main(verbosity=2)
