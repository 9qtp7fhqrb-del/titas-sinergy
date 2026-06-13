#!/usr/bin/env python3
"""
Limpa versões antigas do Firebase Hosting para evitar estouro de cota.
Mantém apenas as KEEP_VERSIONS mais recentes.
Extrai credenciais OAuth diretamente do firebase-tools instalado.
"""
import os, sys, re, subprocess, json

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

SITE          = 'titas-sinergy'
KEEP_VERSIONS = 3
FIREBASE_TOKEN = os.environ.get('FIREBASE_TOKEN', '').strip()


# ── Autenticação ──────────────────────────────────────────────────────────────

def find_credentials_in_firebase_tools():
    """Extrai client_id e client_secret do firebase-tools instalado via npm."""
    try:
        npm_root = subprocess.check_output(
            ['npm', 'root', '-g'], text=True, timeout=15).strip()
        lib_dir = os.path.join(npm_root, 'firebase-tools', 'lib')
        if not os.path.isdir(lib_dir):
            return None, None

        id_re     = re.compile(
            r'clientId["\s:=]+["\'](\d{12,}-[A-Za-z0-9]+\.apps\.googleusercontent\.com)["\']')
        secret_re = re.compile(
            r'clientSecret["\s:=]+["\']([A-Za-z0-9_\-]{10,})["\']')

        for root, dirs, files in os.walk(lib_dir):
            dirs[:] = [d for d in dirs if d != 'node_modules']
            for fname in files:
                if not fname.endswith('.js'):
                    continue
                try:
                    content = open(os.path.join(root, fname), encoding='utf-8',
                                   errors='ignore').read()
                    mid = id_re.search(content)
                    mse = secret_re.search(content)
                    if mid and mse:
                        return mid.group(1), mse.group(1)
                except Exception:
                    pass
    except Exception as e:
        print(f'  Aviso ao buscar credenciais: {e}')
    return None, None


def exchange_token(refresh_token, client_id, client_secret):
    r = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id':     client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type':    'refresh_token',
    }, timeout=30)
    r.raise_for_status()
    return r.json()['access_token']


_NODE_BRIDGE = """
const { execSync } = require('child_process');
const path = require('path');
const fbRoot = execSync('npm root -g').toString().trim();
const candidates = [
  'auth.js',
  path.join('auth', 'index.js'),
  path.join('auth', 'auth.js'),
];
async function run() {
  for (const f of candidates) {
    try {
      const m = require(path.join(fbRoot, 'firebase-tools', 'lib', f));
      const fn = m.getAccessToken || m.refreshAccessToken;
      if (typeof fn !== 'function') continue;
      const r = await fn(process.env.FIREBASE_TOKEN,
        ['https://www.googleapis.com/auth/cloud-platform']);
      const tok = (r && (r.access_token || r.token)) || '';
      if (tok) { console.log(tok); return; }
    } catch(e) {}
  }
  process.exit(1);
}
run().catch(() => process.exit(1));
"""

def get_access_token_via_node(refresh_token):
    try:
        result = subprocess.run(
            ['node', '-e', _NODE_BRIDGE],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'FIREBASE_TOKEN': refresh_token})
        tok = result.stdout.strip()
        if result.returncode == 0 and tok:
            return tok
    except Exception as e:
        print(f'  Node.js bridge falhou: {e}')
    return None


def get_access_token():
    print('  Extraindo credenciais do firebase-tools instalado...')
    client_id, client_secret = find_credentials_in_firebase_tools()
    if client_id and client_secret:
        print(f'  client_id: {client_id[:30]}…')
        try:
            return exchange_token(FIREBASE_TOKEN, client_id, client_secret)
        except Exception as e:
            print(f'  Falha ao trocar token com credenciais extraídas: {e}')
    else:
        print('  Credenciais não encontradas nos arquivos do firebase-tools')

    print('  Tentando via Node.js bridge...')
    tok = get_access_token_via_node(FIREBASE_TOKEN)
    if tok:
        return tok

    raise Exception('Não foi possível obter access token')


# ── Firebase Hosting API ──────────────────────────────────────────────────────

def list_versions(access_token):
    versions, page_token = [], None
    while True:
        params = {'pageToken': page_token} if page_token else {}
        r = requests.get(
            f'https://firebasehosting.googleapis.com/v1beta1/sites/{SITE}/versions',
            headers={'Authorization': f'Bearer {access_token}'},
            params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        versions += data.get('versions', [])
        page_token = data.get('nextPageToken')
        if not page_token:
            break
    return versions


def delete_version(access_token, name):
    # name = "sites/titas-sinergy/versions/VERSION_ID"
    r = requests.delete(
        f'https://firebasehosting.googleapis.com/v1beta1/{name}',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=30)
    return r.status_code


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not FIREBASE_TOKEN:
        print('FIREBASE_TOKEN não definido — cleanup pulado')
        return

    print('Obtendo access token...')
    try:
        access_token = get_access_token()
        print('  Access token obtido com sucesso')
    except Exception as e:
        print(f'AVISO: {e} — cleanup pulado')
        return

    print('Listando versões do Firebase Hosting...')
    try:
        versions = list_versions(access_token)
    except Exception as e:
        print(f'AVISO: falha ao listar versões ({e}) — cleanup pulado')
        return

    finalized = [v for v in versions if v.get('status') == 'FINALIZED']
    finalized.sort(key=lambda v: v.get('createTime', ''), reverse=True)

    print(f'Versões FINALIZED: {len(finalized)} | Mantendo as {KEEP_VERSIONS} mais recentes')

    to_delete = finalized[KEEP_VERSIONS:]
    if not to_delete:
        print('Nenhuma versão antiga para deletar.')
        return

    deleted = 0
    for v in to_delete:
        name = v.get('name', '')
        # name vem como "projects/-/sites/titas-sinergy/versions/ID"
        # a API de DELETE aceita "sites/titas-sinergy/versions/ID"
        short_name = '/'.join(name.split('/')[-4:]) if name else ''
        try:
            status = delete_version(access_token, short_name)
            ok = 200 <= status < 300
            print(f'  {"OK" if ok else "Status " + str(status)}: {short_name.split("/")[-1]}')
            if ok:
                deleted += 1
        except Exception as e:
            print(f'  Erro ao deletar {short_name}: {e}')

    print(f'Cleanup concluído. Deletadas: {deleted}/{len(to_delete)} versões antigas.')


if __name__ == '__main__':
    main()
