import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import deployment_policy as policy
from creator_registry import load_registry, import_workbook
from sprint_research import save_human_review, load_human_reviews
from build_sprint_artifacts import build
from release_audit import audit_release, manifest_files, forbidden_path, EMAIL

ROOT=Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    def test_shipped_mode_is_public_and_fail_closed(self):
        self.assertEqual(json.loads((ROOT/'deployment_config.json').read_text())['mode'],'public_demo')
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(policy.deployment_mode(),'public_demo')
            with patch.object(policy,'CONFIG_PATH',ROOT/'missing-deployment-config.json'):
                self.assertEqual(policy.deployment_mode(),'public_demo')
        for value in ['','PUBLIC_DEMO','unknown','true','local_dev ']:
            with patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':value}):
                # Only the documented spelling (whitespace aside) can enable local mode.
                self.assertEqual(policy.is_local_development(),value.strip()=='local_dev')

    def test_invalid_json_and_session_input_cannot_enable_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json';path.write_text('broken',encoding='utf-8')
            with patch.dict(os.environ,{},clear=True),patch.object(policy,'CONFIG_PATH',path):
                self.assertFalse(policy.is_local_development())
        with patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'public_demo'}):
            with self.assertRaises(PermissionError):policy.require_server_write('test')
            from sprint_ui import parse_campaign_config
            cfg=json.loads((ROOT/'campaign_config.json').read_text(encoding='utf-8'))
            cfg.pop('creator_registry_directory',None)
            cfg['mode']='local_dev'
            with self.assertRaisesRegex(ValueError,'未知字段'):
                parse_campaign_config(json.dumps(cfg).encode('utf-8'))
            self.assertFalse(policy.is_local_development())

    def test_all_business_file_write_sinks_block_before_io(self):
        tables=load_registry()
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'public_demo'}):
            target=Path(folder)/'must-not-exist'
            with patch('creator_registry.read_source_workbook') as reader:
                with self.assertRaises(PermissionError):import_workbook(directory=target)
                reader.assert_not_called()
            with self.assertRaises(PermissionError):save_human_review(tables,{},'test','test',directory=target)
            with self.assertRaises(PermissionError):build(target)
            self.assertFalse(target.exists())

    def test_public_mode_never_loads_private_review_logs(self):
        tables=load_registry()
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'public_demo'}):
            (Path(folder)/'private.json').write_text('deliberately invalid JSON',encoding='utf-8')
            result=load_human_reviews(tables,folder)
            self.assertIs(result,tables)

    def test_local_mode_allows_guard_but_unknown_mode_denies(self):
        with patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'local_dev'}):
            self.assertTrue(policy.is_local_development())
            policy.require_server_write('local test')
        with patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'local'}):
            with self.assertRaises(PermissionError):policy.require_server_write('local test')

    def test_public_research_view_is_read_only_and_has_52_records(self):
        with patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'public_demo'}):
            app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=90).run()
            app.radio(key='presentation_mode').set_value('Research Workspace').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get('form')),0)
            self.assertFalse(any('保存人工审核'==b.label or '保存这条人工证据'==b.label for b in app.button))
            self.assertTrue(any(len(d.value)==52 and 'categories' in d.value for d in app.dataframe))
            self.assertTrue(any('公开展示模式' in e.value for e in app.caption))

    def test_release_manifest_is_complete_private_free_and_import_closed(self):
        result=audit_release(ROOT,check_git=False)
        self.assertEqual(result['errors'],[])
        self.assertEqual(len(result['files']),len(set(result['files'])))
        fixture=json.loads((ROOT/'tests/fixtures/registry_source.json').read_text(encoding='utf-8'))
        self.assertEqual(len(fixture),3)
        self.assertTrue(all(row['creator_id'].startswith('TEST-') for row in fixture))
        self.assertFalse(EMAIL.search(json.dumps(fixture)))

    def test_forbidden_file_classes_are_never_allowed(self):
        for name in ['data/private.xlsx','report.pdf','.venv/python.exe','.env','.env.local',
                     '.streamlit/secrets.toml','secrets.json','backup/a.csv',
                     'data/creator_registry/human_reviews/a.json','credential.pem','temporary.tmp']:
            self.assertTrue(forbidden_path(name),name)
        for name in manifest_files(ROOT):self.assertFalse(forbidden_path(name),name)

    def test_privacy_scanner_rejects_contact_values_without_echoing_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            contact='owner'+'@'+'example.invalid'
            (root/'release_whitelist.txt').write_text('contact.csv\n',encoding='utf-8')
            (root/'contact.csv').write_text('email,checked_by\n'+contact+',Synthetic Reviewer\n',encoding='utf-8')
            result=audit_release(root,check_git=False)
            text='\n'.join(result['errors'])
            self.assertIn('邮箱',text)
            self.assertIn('审核人员字段',text)
            self.assertNotIn(contact,text)

    def test_privacy_scanner_rejects_token_values_without_echoing_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            token='sk-'+'x'*30
            (root/'release_whitelist.txt').write_text('unsafe.txt\n',encoding='utf-8')
            (root/'unsafe.txt').write_text(token,encoding='utf-8')
            text='\n'.join(audit_release(root,check_git=False)['errors'])
            self.assertIn('凭据',text)
            self.assertNotIn(token,text)


if __name__=='__main__':unittest.main()
