import io
import json
import tarfile
from pathlib import Path

from app.config import get_settings
from app.db import reader, transaction
from app.instance_lock import instance_lock
from app.notify import emit
from app.storage import LocalStorage
from scripts.backup import create_backup, restore_backup, sha
from tests.local_support import LocalDatabaseCase
from tests.core_support import CoreApiCase


class BackupTests(LocalDatabaseCase):
    def test_backup_restore_integrity_retention_and_live_guard(self):
        key=LocalStorage().put(b'Synthetic backup content')
        name=create_backup()
        with transaction() as c:
            c.execute("UPDATE institutions SET name='Changed after backup' WHERE id='ins'")
        LocalStorage()._path(key).unlink()
        with instance_lock(get_settings().data_dir):
            with self.assertRaises(OSError):
                restore_backup(name)
        with instance_lock(get_settings().data_dir,'.job-test.lock'):
            with self.assertRaises(OSError):
                restore_backup(name)
        restore_backup(name)
        self.assertEqual(LocalStorage().get(key),b'Synthetic backup content')
        with reader() as c:
            self.assertEqual(c.execute("SELECT name FROM institutions WHERE id='ins'").fetchone()[0],'Synthetic institute')
        for _ in range(14):
            create_backup()
        self.assertEqual(len(list((get_settings().data_dir/'backups').glob('backup-*.json'))),14)
        self.assertTrue((get_settings().data_dir/'backups/last_success.json').exists())

    def test_restore_refuses_corruption_and_archive_traversal(self):
        name=create_backup()
        root=get_settings().data_dir/'backups'
        file=root/(name+'.tar.gz')
        file.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            restore_backup(name)
        with tarfile.open(file,'w:gz') as tar:
            member=tarfile.TarInfo('../escape')
            member.size=3
            tar.addfile(member,io.BytesIO(b'bad'))
        manifest=json.loads((root/(name+'.json')).read_text())
        manifest['sha256'][file.name]=sha(file)
        (root/(name+'.json')).write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            restore_backup(name)
        self.assertFalse((get_settings().data_dir/'escape').exists())
        with self.assertRaises(ValueError):
            restore_backup('../escape')

    def test_emit_filters_institutions_and_unsubmitted_staff(self):
        with transaction() as c:
            c.execute("INSERT INTO institutions (id,aicte_permanent_id,name,state,trust_name,created_at) VALUES ('other','TEST-OTHER','Other synthetic','Test','Trust','2026-01-01')")
            c.execute("INSERT INTO users (id,email,name,role,institution_id,password_hash,created_at) VALUES ('foreign','foreign@example.test','Other','INSTITUTION','other','!unused','2026-01-01')")
            c.execute("INSERT INTO users (id,email,name,role,password_hash,created_at) VALUES ('off','off@example.test','Officer','OFFICER','!unused','2026-01-01')")
            ids=emit(c,to_users=['usr','foreign'],kind='TEST',title='Synthetic notice',body='Synthetic',link='/applications/app',application_id='app')
            self.assertEqual(len(ids),1)
            c.execute("UPDATE applications SET submitted_at=NULL WHERE id='app'")
            self.assertEqual(emit(c,to_role='OFFICER',kind='TEST',title='Synthetic',body='Synthetic',link='/applications/app',application_id='app'),[])


class ObservabilityTests(CoreApiCase):
    def test_metrics_token_and_json_log_redaction(self):
        self.assertEqual(self.client.get(self.base+'/metrics').status_code,401)
        self.assertEqual(self.client.get(self.base+'/metrics',headers={'Authorization':'Bearer wrong'}).status_code,401)
        r=self.client.get(self.base+'/metrics',headers={'Authorization':'Bearer '+self.metrics_token})
        self.assertEqual(r.status_code,200)
        for metric in ('pramaan_requests_total','pramaan_queue_depth','pramaan_email_failures_total','pramaan_job_stage_seconds'):
            self.assertIn(metric,r.text)
        marker='synthetic-secret-query-marker'
        self.client.get(self.base+'/health?token='+marker)
        logs=(Path(self.tmp.name)/'server.log').read_text(encoding='utf-8')
        self.assertNotIn(marker,logs)
        records=[json.loads(line) for line in logs.splitlines() if line.startswith('{')]
        self.assertTrue(records)
        self.assertTrue(all('route' in r and 'user_id_hash' in r for r in records))
