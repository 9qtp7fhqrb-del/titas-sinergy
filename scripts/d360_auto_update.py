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
        os.path.expanduser('~/.npm-global/bin/firebase'),
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

def dentro_do_horario():
    """Seg-Sáb 09:30-23:00 | Dom 14:00-22:00"""
    now = datetime.now()
    wd = now.weekday()  # 0=seg … 6=dom
    h = now.hour + now.minute / 60
    if wd == 6:  # domingo
        return 14.0 <= h < 22.0
    else:        # seg a sáb
        return 9.5 <= h < 23.0

def main():
    if not dentro_do_horario():
        log('fora do horário — pulando')
        return
    log('iniciando atualização local')

    env = os.environ.copy()
    env['PATH'] = '/Users/marcelolima/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin'
    env['HOME'] = os.path.expanduser('~')
    env['PYTHONUNBUFFERED'] = '1'

    # Lê credenciais do arquivo apenas se env vars do plist não estiverem definidas
    # (evita EDEADLK em ~/Documents/ quando LaunchAgent já tem as credenciais no plist)
    if not env.get('ERP_LOGIN') or not env.get('ERP_PASSWORD'):
        cred_path = os.path.expanduser('~/Documents/D360-Vendas/.erp-credentials.json')
        if os.path.exists(cred_path):
            import json as _json
            try:
                with open(cred_path, 'r') as _f:
                    _creds = _json.load(_f)
                env['ERP_LOGIN']    = _creds.get('login', '')
                env['ERP_PASSWORD'] = _creds.get('password', '')
            except Exception as e:
                log(f'AVISO: não foi possível ler credenciais: {e}')

    import tempfile

    def run_captured(cmd, timeout=600, cwd_override=None):
        """subprocess sem pipes (evita deadlock macOS LaunchAgent)."""
        import tempfile as _tf
        out_path = _tf.mktemp(suffix='.out')
        err_path = _tf.mktemp(suffix='.err')
        try:
            out_fh = open(out_path, 'w')
            err_fh = open(err_path, 'w')
            rc = subprocess.run(cmd, cwd=cwd_override or PROJECT, env=env,
                                stdout=out_fh, stderr=err_fh,
                                close_fds=True, timeout=timeout).returncode
            out_fh.close()
            err_fh.close()
            out = open(out_path).read()
            err = open(err_path).read()
        finally:
            for p in (out_path, err_path):
                try: os.unlink(p)
                except: pass
        return rc, out, err

    # 1. Roda update_d360.py
    script = os.path.join(PROJECT, 'scripts', 'update_d360.py')
    try:
        rc, out, err = run_captured([sys.executable, script], timeout=900)
    except Exception as _te:
        log(f'ERRO run_captured: {_te}')
        return
    for line in out.strip().split('\n'):
        if line: log(f'  [update] {line}')
    for line in err.strip().split('\n'):
        if line and 'NotOpenSSLWarning' not in line and 'urllib3' not in line:
            log(f'  [update-err] {line}')

    if rc != 0:
        log(f'ERRO no update_d360.py (exit {rc})')
        return

    log('update OK — fazendo deploy...')

    # 2. Firebase deploy — copia os arquivos do site para /tmp/ e publica dali,
    #    evitando restrição TCC do macOS que bloqueia Node.js de ler ~/Documents/.
    import json as _json
    firebase_cmd = find_firebase()
    tmp_dir  = '/tmp/titas-firebase-deploy'
    pub_dir  = '/tmp/titas-firebase-pub'   # pasta com os arquivos reais do site
    deploy_ok = False

    def _safe_copy(src, dst):
        """Copia via open/read/write — evita EDEADLK do TCC em LaunchAgent."""
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, 'rb') as _f:
            data = _f.read()
        with open(dst, 'wb') as _f:
            _f.write(data)

    def _safe_rmtree(path):
        for root, dirs, files in os.walk(path, topdown=False):
            for f in files:
                try: os.remove(os.path.join(root, f))
                except: pass
            for d in dirs:
                try: os.rmdir(os.path.join(root, d))
                except: pass
        try: os.rmdir(path)
        except: pass

    try:
        os.makedirs(tmp_dir, exist_ok=True)
        # Recria pasta pública do zero para garantir versão fresca
        if os.path.exists(pub_dir):
            _safe_rmtree(pub_dir)
        os.makedirs(pub_dir)
        # Copia arquivos que compõem o site (open/read/write evita TCC EDEADLK)
        for _fname in ('index.html', 'sw.js', '404.html', 'favicon.svg'):
            _src = os.path.join(PROJECT, _fname)
            if os.path.isfile(_src):
                _safe_copy(_src, os.path.join(pub_dir, _fname))
        _assets_src = os.path.join(PROJECT, 'assets')
        if os.path.isdir(_assets_src):
            for _root, _dirs, _files in os.walk(_assets_src):
                for _af in _files:
                    _asrc = os.path.join(_root, _af)
                    _arel = os.path.relpath(_asrc, PROJECT)
                    _safe_copy(_asrc, os.path.join(pub_dir, _arel))
        # firebase.json com public apontando para /tmp/ — Node.js só lê daqui
        deploy_cfg = {
            'hosting': {
                'public': pub_dir,
                'ignore': ['firebase.json', '**/.*', '**/node_modules/**'],
                'headers': [
                    {'source': '/sw.js', 'headers': [{'key': 'Cache-Control', 'value': 'no-cache, no-store, must-revalidate'}]},
                    {'source': '/index.html', 'headers': [
                        {'key': 'Cache-Control', 'value': 'no-store, no-cache, must-revalidate, max-age=0'},
                        {'key': 'Pragma', 'value': 'no-cache'},
                        {'key': 'Expires', 'value': '0'}
                    ]},
                    {'source': '/', 'headers': [
                        {'key': 'Cache-Control', 'value': 'no-store, no-cache, must-revalidate, max-age=0'},
                        {'key': 'Pragma', 'value': 'no-cache'},
                        {'key': 'Expires', 'value': '0'}
                    ]}
                ]
            }
        }
        with open(os.path.join(tmp_dir, 'firebase.json'), 'w') as _f:
            _json.dump(deploy_cfg, _f)
        with open(os.path.join(tmp_dir, '.firebaserc'), 'w') as _f:
            _json.dump({'projects': {'default': 'titas-sinergy'}}, _f)
        deploy_ok = True
    except Exception as e:
        log(f'AVISO: erro ao preparar deploy: {e}')

    if not deploy_ok:
        log('ERRO: não foi possível preparar arquivos para deploy — abortando')
        return

    for _tentativa in range(1, 4):   # até 3 tentativas
        rc2, out2, err2 = run_captured(
            firebase_cmd + ['deploy', '--only', 'hosting', '--project', 'titas-sinergy'],
            timeout=180,
            cwd_override=tmp_dir
        )
        for line in out2.strip().split('\n'):
            if line and any(kw in line for kw in ['Hosting URL', 'Deploy complete', 'Error', 'error', 'complete']):
                log(f'  [deploy] {line}')
        if rc2 == 0:
            log('deploy concluído com sucesso')
            break
        log(f'ERRO no deploy tentativa {_tentativa}/3 (exit {rc2})')
        if err2:
            log(f'  {err2[:200]}')
        if _tentativa < 3:
            import time as _time; _time.sleep(15)

if __name__ == '__main__':
    main()
