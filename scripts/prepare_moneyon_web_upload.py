"""Produce separate HF web and dedicated GitHub-repo upload archives, offline."""
import argparse
import json
import shutil
import zipfile
from pathlib import Path
from scripts.prepare_moneyon_space import prepare, ROOT


def archive(folder,target):
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_file():z.write(path,path.relative_to(folder).as_posix())


def package(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new output folder; never overwrite existing files')
    output.mkdir(parents=True)
    hf=output/'huggingface-upload'
    manifest=prepare(hf)
    github=output/'github-upload'
    shutil.copytree(hf,github)
    (github/'tools').mkdir()
    shutil.copyfile(ROOT/'deploy/moneyon/github/sync_moneyon.py',github/'tools/sync_moneyon.py')
    shutil.copyfile(ROOT/'scripts/check_moneyon_space.py',github/'tools/check_moneyon_space.py')
    (github/'.github/workflows').mkdir(parents=True)
    shutil.copyfile(ROOT/'deploy/moneyon/github/deploy-moneyon.yml',github/'.github/workflows/deploy-moneyon.yml')
    # Keep the GitHub controller and metadata out of Docker build context.
    with (github/'.dockerignore').open('a',encoding='utf-8') as f:f.write('.github/\ntools/\n')
    # Both packages have the same application sources; each records its own ignore file hash.
    import hashlib
    ghmanifest=dict(manifest)
    ghmanifest['.dockerignore']=hashlib.sha256((github/'.dockerignore').read_bytes()).hexdigest()
    (github/'manifest.json').write_text(json.dumps(ghmanifest,indent=2),encoding='utf-8')
    files=sorted([*manifest,'manifest.json'])
    (output/'UPLOAD_FILES.txt').write_text('\n'.join(files)+'\n',encoding='utf-8')
    archive(hf,output/'moneyon-huggingface-web.zip')
    archive(github,output/'moneyon-github-web.zip')
    return {'hf_files':len(files),'github_files':len(files)+3,'uploaded':False,'output':str(output)}


if __name__=='__main__':
    # Run from project root with python -m scripts.prepare_moneyon_web_upload.
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    print(json.dumps(package(parser.parse_args().output)))
