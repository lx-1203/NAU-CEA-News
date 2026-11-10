"""Verify the qualified assets shipped in a portable bundle."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def verify(root=ROOT):
    root=Path(root).resolve();manifest=json.loads((root/'assets/qualified-assets.json').read_text('utf8'))
    for item in manifest['items']:
        p=(root/item['path']).resolve()
        if not p.is_relative_to(root) or not p.is_file():raise ValueError('Missing/outside asset: '+item['path'])
        with p.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=item['sha256']:raise ValueError('Asset SHA256 mismatch: '+item['path'])
    return len(manifest['items'])

if __name__=='__main__':print('ASSETS VERIFIED:',verify())
