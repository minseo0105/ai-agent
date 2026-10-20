"""Upload a reviewed MONEY bundle, only after explicit human approval.

Default is a local manifest check. Remote creation/upload requires --publish.
Never uses the existing AI LAB HF_SPACE target or uploads the workspace root.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def validate(folder):
    folder=Path(folder).resolve()
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    files={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if files != set(manifest)|{'manifest.json'}:
        raise ValueError('Bundle has unreviewed files. Prepare a fresh source-only bundle.')
    for name,digest in manifest.items():
        path=folder/name
        if path.is_symlink() or not path.resolve().is_relative_to(folder):
            raise ValueError('Unsafe bundle path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Bundle changed since preparation: '+name)
        if any(part in ('.git','.streamlit','node_modules','data','runtime') or part.startswith('.env') for part in Path(name).parts):
            raise ValueError('Forbidden bundle path')
    if 'sdk: docker' not in (folder/'README.md').read_text(encoding='utf-8'):
        raise ValueError('Expected a dedicated Docker Space')
    return folder,manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True)
    parser.add_argument('--space',required=True,help='OWNER/moneyon-demo (separate from AI LAB)')
    parser.add_argument('--publish',action='store_true',help='Only after human approval')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+',args.space):
        parser.error('Expected OWNER/SPACE')
    if args.space==os.environ.get('HF_SPACE'):
        parser.error('The existing AI LAB Space cannot be the MONEY target')
    folder,manifest=validate(args.bundle)
    print(json.dumps({'space':args.space,'files':len(manifest),'publish':args.publish,'bundle':str(folder)}))
    if not args.publish:
        print('Dry run only. No Hugging Face request was made.')
        return
    from huggingface_hub import HfApi, get_token
    token=os.environ.get('HF_TOKEN') or get_token()
    if not token:parser.error('Run hf auth login locally; never put credentials in the bundle.')
    api=HfApi(token=token)
    owner=api.whoami()['name']
    if args.space != owner+'/moneyon-demo':
        parser.error('Only the signed-in owner/moneyon-demo target is allowed.')
    # Existing repos are rejected: prevents accidental updates to other agents.
    api.create_repo(args.space,repo_type='space',space_sdk='docker',private=False,exist_ok=False)
    api.upload_folder(repo_id=args.space,repo_type='space',folder_path=str(folder),commit_message='Publish reviewed MONEY trial-only Space')
    print('Created: https://huggingface.co/spaces/'+args.space)
    print('Get the exact app URL from Space → Embed this Space; typical https://OWNER-SPACE.hf.space/')


if __name__=='__main__':main()
