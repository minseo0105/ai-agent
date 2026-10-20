"""GitHub-only sync to an existing, manually created MONEY Docker Space.

No CLI login, repository creation, deletes, secrets/variables or hardware changes.
Only files named in the reviewed source manifest are uploaded.
"""
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath


def validate(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError('Unsafe manifest path')
        if any(p in ('.git','.github','tools','data','runtime','node_modules','.streamlit') or p.startswith('.env') for p in relative.parts):
            raise ValueError('Forbidden upload path')
        path=root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Unsafe source file')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Source manifest mismatch: '+name)
    if not {'Dockerfile','README.md','space_app.py','requirements.txt'} <= manifest.keys():
        raise ValueError('Incomplete MONEY bundle')
    return sorted([*manifest,'manifest.json'])


def sync(root,space,api):
    if not re.fullmatch(r'[A-Za-z0-9_-]+/moneyon-demo',space):
        raise ValueError('Only OWNER/moneyon-demo is allowed')
    files=validate(root)
    if api.whoami()['name'].lower()!=space.split('/')[0].lower():
        raise ValueError('Use the personal owner of the manually created Space')
    info=api.space_info(space)
    if info.sdk!='docker':raise ValueError('Target must already be a Docker Space')
    remote=set(api.list_repo_files(space,repo_type='space'))
    if remote-set(files)-{'.gitattributes'}:
        raise ValueError('Unexpected remote files: refusing to overwrite an unrelated app')
    # No delete_patterns and no repo-wide sync. Workflow/tools/secrets excluded.
    return api.upload_folder(repo_id=space,repo_type='space',folder_path=str(root),
                             allow_patterns=files,commit_message='Sync reviewed MONEY trial-only source')


if __name__=='__main__':
    from huggingface_hub import HfApi
    root=Path(__file__).resolve().parents[1]
    token=os.environ.get('MONEYON_HF_TOKEN')
    space=os.environ.get('MONEYON_HF_SPACE','')
    if not token:raise SystemExit('Set MONEYON_HF_TOKEN in GitHub Secrets')
    sync(root,space,HfApi(token=token))
    print('Synced MONEY files to https://huggingface.co/spaces/'+space)
