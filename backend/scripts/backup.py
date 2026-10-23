"""Online SQLite and private-store backups. Restore requires a stopped instance.

Usage: python -m scripts.backup [--restore backup-YYYYMMDDTHHMMSS-xxxxxxxx]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing, ExitStack
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.config import get_settings
from app.db import now_iso, reader
from app.instance_lock import instance_lock

NAME=re.compile(r'backup-\d{8}T\d{6}-[a-f0-9]{8}')


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def s3_client():
    import boto3  # optional; only backup upload uses this dependency
    s=get_settings()
    return boto3.client('s3',endpoint_url=s.backup_s3_endpoint,aws_access_key_id=s.backup_s3_key_id,
                        aws_secret_access_key=s.backup_s3_secret)


def create_backup():
    s=get_settings()
    root=s.data_dir/'backups'
    root.mkdir(parents=True,exist_ok=True)
    name='backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]
    with tempfile.TemporaryDirectory(dir=root,prefix='.creating-') as tmp:
        temp=Path(tmp)
        database=temp/(name+'.sqlite3')
        with reader() as source, closing(sqlite3.connect(database)) as target:
            source.backup(target)
        archive=temp/(name+'.tar.gz')
        with tarfile.open(archive,'w:gz') as tar:
            if s.storage_dir.exists():
                for file in sorted(s.storage_dir.rglob('*')):
                    if file.is_symlink():
                        raise ValueError('Storage symlinks are not supported')
                    if file.is_file() and file.suffix!='.tmp':
                        tar.add(file,arcname=file.relative_to(s.storage_dir).as_posix(),recursive=False)
        manifest={'name':name,'at':now_iso(),'sha256':{database.name:sha(database),archive.name:sha(archive)}}
        meta=temp/(name+'.json')
        meta.write_text(json.dumps(manifest),encoding='utf-8')
        files=[database,archive,meta]
        if s.backup_s3_bucket:
            client=s3_client()
            for file in files:
                client.upload_file(str(file),s.backup_s3_bucket,'pramaan-backups/'+file.name)
        for file in files:
            os.chmod(file,0o600)
            file.replace(root/file.name)
    (root/'last_success.json').write_text(json.dumps({'at':manifest['at'],'name':name}),encoding='utf-8')
    completed=sorted(p.stem for p in root.glob('backup-*.json') if NAME.fullmatch(p.stem))
    for old in completed[:-14]:
        for suffix in ('.sqlite3','.tar.gz','.json'):
            (root/(old+suffix)).unlink(missing_ok=True)
    if s.backup_s3_bucket:
        keys=[]
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=s.backup_s3_bucket,Prefix='pramaan-backups/'):
            keys.extend(x['Key'] for x in page.get('Contents',[]))
        names=sorted(k.rsplit('/',1)[-1][:-5] for k in keys if k.endswith('.json') and NAME.fullmatch(k.rsplit('/',1)[-1][:-5]))
        for old in names[:-14]:
            client.delete_objects(Bucket=s.backup_s3_bucket,Delete={'Objects':[{'Key':f'pramaan-backups/{old}{suffix}'} for suffix in ('.sqlite3','.tar.gz','.json')]})
    return name


def restore_backup(name):
    if not NAME.fullmatch(name):
        raise ValueError('Invalid backup name')
    s=get_settings()
    root=s.data_dir/'backups'
    with instance_lock(s.data_dir), ExitStack() as locks:
        # Interrupted servers can have a processing subprocess still shutting down.
        for guard in s.data_dir.glob('.job-*.lock'):
            locks.enter_context(instance_lock(s.data_dir,guard.name))
        meta=root/(name+'.json')
        if not meta.exists() and s.backup_s3_bucket:
            root.mkdir(parents=True,exist_ok=True)
            client=s3_client()
            for suffix in ('.sqlite3','.tar.gz','.json'):
                client.download_file(s.backup_s3_bucket,f'pramaan-backups/{name}{suffix}',str(root/(name+suffix)))
        manifest=json.loads(meta.read_text(encoding='utf-8'))
        for suffix in ('.sqlite3','.tar.gz'):
            file=root/(name+suffix)
            if manifest['sha256'].get(file.name)!=sha(file):
                raise ValueError('Backup integrity check failed')
        with closing(sqlite3.connect(root/(name+'.sqlite3'))) as check:
            if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('Database integrity check failed')
        with tempfile.TemporaryDirectory(dir=s.data_dir,prefix='.restore-') as tmp:
            staging=Path(tmp)/'files'
            staging.mkdir()
            with tarfile.open(root/(name+'.tar.gz'),'r:gz') as tar:
                for member in tar.getmembers():
                    path=PurePosixPath(member.name)
                    if not member.isfile() or path.is_absolute() or '..' in path.parts or '\\' in member.name or ':' in member.name:
                        raise ValueError('Unsafe archive entry')
                    target=staging.joinpath(*path.parts)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with tar.extractfile(member) as source,target.open('wb') as out:
                        shutil.copyfileobj(source,out)
            # The content-addressed store is immutable: restoration can retain unrelated objects safely.
            s.storage_dir.mkdir(parents=True,exist_ok=True)
            for source in staging.rglob('*'):
                if source.is_file():
                    target=s.storage_dir/source.relative_to(staging)
                    if not target.resolve().is_relative_to(s.storage_dir.resolve()):
                        raise ValueError('Storage path escapes the private store')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    source.replace(target)
            s.database_path.parent.mkdir(parents=True,exist_ok=True)
            replacement=s.database_path.with_suffix('.restore-tmp')
            shutil.copyfile(root/(name+'.sqlite3'),replacement)
            for suffix in ('-wal','-shm'):
                Path(str(s.database_path)+suffix).unlink(missing_ok=True)
            replacement.replace(s.database_path)
    return name


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--restore')
    args=ap.parse_args()
    print(restore_backup(args.restore) if args.restore else create_backup())


if __name__=='__main__':
    main()
