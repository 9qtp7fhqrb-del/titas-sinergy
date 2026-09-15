#!/usr/bin/env python3
"""
D360 Auto-Update Local
Roda update_d360.py + firebase deploy automaticamente.
Executado pelo LaunchAgent com.titas.d360local a cada 30 min.
"""
import os, sys, subprocess, time
from datetime import datetime

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(PROJECT, '.d360-local.log')

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"{ts} — {msg}"
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')

def find_firebase():
    candidates = [
        '/usr/local/bin/firebase',
        '/opt/homebrew/bin/firebase',
        os.path.expanduser('~/.npm/bin/firebase'),
        os.path.expanduser('~/node_modules/.bin/firebase'),
    ]
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return [p]
    # fallback: npx
    return ['npx', '--yes', 'firebase-tools']

def main():
    log('iniciando atualização local')

    env = os.environ.copy()
    env['PATH'] = '/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin'
    env['HOME'] = os.path.expanduser('~')

    import tempfile

    def run_captured(cmd, timeout=600):
        """subprocess sem pipes (evita deadlock macOS LaunchAgent)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as out_f, \
             tempfile.NamedTemporaryFile(mode='w', suffix='.err', delete=False) as err_f:
            out_path, err_path = out_f.name, err_f.name
        try:
            rc = subprocess.run(cmd, cwd=PROJECT, env=env,
                                stdout=open(out_path, 'w'),
                                stderr=open(err_path, 'w'),
                                timeout=timeout).returncode
            out = open(out_path).read()
            err = open(err_path).read()
        finally:
            for p in (out_path, err_path):
                try: os.unlink(p)
                except: pass
        return rc, out, err

    # 1. Roda update_d360.py
    script = os.path.join(PROJECT, 'scripts', 'update_d360.py')
    rc, out, err = run_captured([sys.executable, script])
    for line in out.strip().split('\n'):
        if line: log(f'  [update] {line}')
    for line in err.strip().split('\n'):
        if line and 'NotOpenSSLWarning' not in line and 'urllib3' not in line:
            log(f'  [update-err] {line}')

    if rc != 0:
        log(f'ERRO no update_d360.py (exit {rc})')
        return

    log('update OK — fazendo deploy...')

    # 2. Firebase deploy
    firebase_cmd = find_firebase()
    rc2, out2, err2 = run_captured(
        firebase_cmd + ['deploy', '--only', 'hosting', '--project', 'titas-sinergy'],
        timeout=120
    )
    for line in out2.strip().split('\n'):
        if line and any(kw in line for kw in ['Hosting URL', 'Deploy complete', 'Error', 'error']):
            log(f'  [deploy] {line}')
    if rc2 == 0:
        log('deploy concluído com sucesso')
    else:
        log(f'ERRO no deploy (exit {rc2})')
        if err2:
            log(f'  {err2[:300]}')

if __name__ == '__main__':
    main()
