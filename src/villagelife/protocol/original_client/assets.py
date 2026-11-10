"""On-demand access to user-supplied XAPK/OBB files, never shipped in Git.

A read-only manifest is extracted from the original APK inside the user's
XAPK. Expansion data uses a separately provided OBB and authored inventory.
"""
from __future__ import annotations
from pathlib import Path
import csv
import io
import zipfile

class ClientAssets:
    def __init__(self, *, xapk:Path|None=None, obb:Path|None=None, inventory:Path|None=None):
        self.manifest=None
        self.obb=Path(obb).resolve(strict=True) if obb else None
        self.entries={}
        if xapk:
            with zipfile.ZipFile(Path(xapk).resolve(strict=True)) as container:
                apk_names=[n for n in container.namelist() if n.endswith('.apk') and '/' not in n]
                if len(apk_names)!=1:raise ValueError('Expected one root Android APK inside XAPK')
                with zipfile.ZipFile(io.BytesIO(container.read(apk_names[0]))) as apk:
                    self.manifest=apk.read('assets/origmanifest.xml')
        if inventory:
            with Path(inventory).open(newline='',encoding='utf-8-sig') as fd:
                for row in csv.DictReader(fd):
                    name=row['path']
                    if not name.startswith('files/') or '..' in name.split('/'):
                        raise ValueError('Invalid authored resource path')
                    self.entries[name]=(int(row['offset_in_tcf']),int(row['stored_bytes']))
        if bool(self.obb) != bool(inventory):
            raise ValueError('Both OBB and authored inventory are required for resource serving')

    def content(self, path:str)->bytes|None:
        if self.obb is None:return None
        target=path[path.index('files/'):] if 'files/' in path else path.lstrip('/')
        span=self.entries.get(target)
        if span is None:return None
        off,size=span
        if size<0 or size>128*1024*1024 or off<0:
            raise ValueError('Invalid authored resource range')
        with self.obb.open('rb') as fd:
            fd.seek(0,2)
            if off+size>fd.tell():raise ValueError('Resource range outside OBB')
            fd.seek(off)
            return fd.read(size)
