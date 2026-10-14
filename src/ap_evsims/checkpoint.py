"""Bounded, secret-scanned Git checkpoints. Failures never roll back local research."""
import json,os,re,shutil,subprocess,sys
from pathlib import Path
from urllib.parse import quote,quote_plus
from .providers.security import CREDENTIAL_NAMES,load_credentials

SAFE_ROOT_FILES={'.gitignore','.gitattributes','.env.example','pyproject.toml','TASK_STATE.json'}
SAFE_DIRS={'src','tests','examples','reports','outputs'}
SUFFIXES={'.py','.md','.json','.jsonl','.txt','.toml','.csv','.yml','.yaml'}

def scan_bytes(name,body,secrets):
    path=Path(name)
    if path.name.startswith('.env') and name!='.env.example':raise ValueError('ENV_FILE_NOT_ALLOWED')
    if any(part in ('.git','.venv','__pycache__','data') for part in path.parts):raise ValueError('DATA_OR_RUNTIME_NOT_ALLOWED')
    if len(body)>5_000_000:raise ValueError('CHECKPOINT_FILE_TOO_LARGE')
    if b'\x00' in body:raise ValueError('BINARY_FILE_NOT_ALLOWED')
    text=body.decode('utf-8')
    for secret in secrets:
        if secret and any(value in text for value in (secret,quote(secret,safe=''),quote_plus(secret))):raise ValueError('SECRET_SCAN_FAILED')
    patterns=(r'(?i)(?:CFBD_API_KEY|THE_ODDS_API_KEY)\s*=\s*["\x27]?[A-Za-z0-9_+/=]{20,}',
        r'(?i)apiKey=[A-Za-z0-9]{20,}',r'(?i)(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    if any(re.search(pattern,text) for pattern in patterns):raise ValueError('SECRET_SCAN_FAILED')
    if path.suffix=='.json':json.loads(text)

def safe_files(repo):
    repo=Path(repo).resolve();files=[]
    candidates=list(repo.iterdir())
    for folder in SAFE_DIRS:
        root=repo/folder
        if root.is_symlink() or not root.is_dir():continue
        for directory,dirs,names in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if d not in ('.git','.venv','__pycache__','data','build','dist')
                and not d.endswith('.egg-info') and not (Path(directory)/d).is_symlink()]
            candidates.extend(Path(directory)/name for name in names)
    for path in candidates:
        relative=path.relative_to(repo)
        if path.is_symlink() or not path.is_file() or any(p in ('.git','.venv','__pycache__','data') for p in relative.parts):continue
        if repo not in path.resolve().parents:raise ValueError('CHECKPOINT_PATH_ESCAPE')
        if (len(relative.parts)==1 and (path.name in SAFE_ROOT_FILES or path.suffix in ('.md','.txt'))) or (relative.parts[0] in SAFE_DIRS and path.suffix in SUFFIXES):files.append(relative.as_posix())
    return sorted(files)

def resolve_git(explicit=None):
    if explicit:return explicit
    found=shutil.which('git')
    if found:return found
    bundled=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
    return str(bundled) if bundled.is_file() else None

def source_head(repo,git=None):
    git=resolve_git(git)
    if not git:return None
    try:
        result=subprocess.run([git,'-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,timeout=10)
        value=result.stdout.strip()
        return value if result.returncode==0 and re.fullmatch('[0-9a-f]{40}',value) else None
    except (OSError,subprocess.TimeoutExpired):return None

def run_full_tests(repo):
    repo=Path(repo).resolve();temporary=repo/'data/evaluations/test_tmp';temporary.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(PYTHONPATH=str(repo/'src'),TEMP=str(temporary),TMP=str(temporary))
    code="import unittest,io,json; s=unittest.defaultTestLoader.discover('tests'); r=unittest.TextTestRunner(stream=io.StringIO()).run(s); print(json.dumps(dict(ran=r.testsRun,failed=len(r.failures)+len(r.errors),skipped=len(r.skipped)))); raise SystemExit(not r.wasSuccessful())"
    try:result=subprocess.run([sys.executable,'-c',code],cwd=repo,env=env,capture_output=True,text=True,timeout=300)
    except (OSError,subprocess.TimeoutExpired):return dict(passed=0,failed=1,status='TEST_RUN_UNAVAILABLE')
    try:counts=json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):return dict(passed=0,failed=1,status='TEST_RESULT_UNREADABLE')
    return dict(passed=counts['ran']-counts['failed']-counts['skipped'],failed=counts['failed'],skipped=counts['skipped'],status='PASS' if result.returncode==0 else 'FAIL')

def commit_and_push(repo, *, git=None,push=True,author_name=None,author_email=None):
    """Call only after successful full tests. Credentials never enter reports or argv."""
    repo=Path(repo).resolve();load_credentials(repo/'.env')
    git=resolve_git(git)
    if not git:return dict(status='GIT_EXECUTABLE_UNAVAILABLE',push_success=False)
    env=os.environ.copy();env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never',GCM_GUI_PROMPT='false')
    for key in list(env):
        if key.startswith(('GIT_TRACE','GCM_TRACE')):env.pop(key)
    def call(*args,timeout=45):return subprocess.run([str(git),'-C',str(repo),*args],env=env,capture_output=True,timeout=timeout)
    def read(*args):
        result=call(*args)
        if result.returncode:raise ValueError('GIT_READ_FAILED')
        return result.stdout.decode('utf-8').strip()
    try:
        branch=read('branch','--show-current');remote=read('remote','get-url','origin')
        if branch!='ap-evisims-live' or remote!='https://github.com/adrianopalaia-arch/AP-EV-SIMS.git':return dict(status='GIT_TARGET_MISMATCH',push_success=False)
        secrets=[os.environ.get(k,'') for k in CREDENTIAL_NAMES]
        files=safe_files(repo)
        for name in files:scan_bytes(name,(repo/name).read_bytes(),secrets)
        # Explicit allowlist; raw data, databases, environments and huge files cannot enter.
        added=call('add','--',*files)
        if added.returncode:return dict(status='GIT_STAGE_FAILED',push_success=False)
        staged=read('diff','--cached','--name-only','-z').strip('\x00').split('\x00')
        for name in filter(None,staged):
            if name not in files:raise ValueError('UNEXPECTED_STAGED_FILE')
            content=call('show',':'+name)
            if content.returncode:raise ValueError('STAGED_READ_FAILED')
            scan_bytes(name,content.stdout,secrets)
        if any(staged):
            args=[]
            if author_name and author_email:args=['-c','user.name='+author_name,'-c','user.email='+author_email]
            committed=call(*args,'commit','-m','Checkpoint AP EV/SIMS tested research and status')
            if committed.returncode:return dict(status='GIT_COMMIT_FAILED',push_success=False)
        commit=read('rev-parse','HEAD')
        result=call('push','-u','origin',branch) if push else None
        return dict(status='PUSH_SUCCESS' if result and result.returncode==0 else 'LOCAL_COMMIT_SAVED' if not push else 'PUSH_BLOCKED',
            push_success=bool(result and result.returncode==0),branch=branch,commit=commit,env_staged=False,secret_scan='PASS')
    except (ValueError,UnicodeError):return dict(status='CHECKPOINT_SAFETY_CHECK_FAILED',push_success=False)
    except (OSError,subprocess.TimeoutExpired):return dict(status='GIT_ACCESS_UNAVAILABLE_OR_TIMEOUT',push_success=False)
