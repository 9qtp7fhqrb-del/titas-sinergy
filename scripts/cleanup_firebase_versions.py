#!/usr/bin/env python3
"""
Limpa versões antigas do Firebase Hosting para evitar estouro de cota.
Mantém apenas as N versões mais recentes (padrão: 3).
"""
import os, sys, json

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

SITE = 'titas-sinergy'
KEEP_VERSIONS = 3
FIREBASE_TOKEN = os.environ.get('FIREBASE_TOKEN', '').strip()

# Credenciais públicas do Firebase CLI (open source em firebase-tools)
_CLIENT_ID = '563584335869-fgrhgmd47bqnekij5i8b5a0d3651s2j8.apps.googleusercontent.com'
_CLIENT_SECRET = 'j9iVZfS8vu8C56MkGMnNjJW6'


def exchange_token(refresh_token):
    r = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id':     _CLIENT_ID,
        'client_secret': _CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type':    'refresh_token',
    }, timeout=30)
    r.raise_for_status()
    return r.json()['access_token']


def list_versions(access_token):
    versions = []
    url = f'https://firebasehosting.googleapis.com/v1beta1/sites/{SITE}/versions'
    while url:
        r = requests.get(url, headers={'Authorization': f'Bearer {access_token}'}, timeout=30)
        r.raise_for_status()
        data = r.json()
        versions += data.get('versions', [])
        url = data.get('nextPageToken') and \
              f'https://firebasehosting.googleapis.com/v1beta1/sites/{SITE}/versions?pageToken={data["nextPageToken"]}'
    return versions


def delete_version(access_token, name):
    r = requests.delete(
        f'https://firebasehosting.googleapis.com/v1beta1/{name}',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=30
    )
    return r.status_code


def main():
    if not FIREBASE_TOKEN:
        print('FIREBASE_TOKEN não definido — cleanup pulado')
        return

    print('Trocando token Firebase...')
    try:
        access_token = exchange_token(FIREBASE_TOKEN)
    except Exception as e:
        print(f'AVISO: falha na troca de token ({e}) — cleanup pulado')
        return

    print('Listando versões do Firebase Hosting...')
    try:
        versions = list_versions(access_token)
    except Exception as e:
        print(f'AVISO: falha ao listar versões ({e}) — cleanup pulado')
        return

    finalized = [v for v in versions if v.get('status') == 'FINALIZED']
    finalized.sort(key=lambda v: v.get('createTime', ''), reverse=True)

    print(f'Versões finalizadas: {len(finalized)} | Mantendo as {KEEP_VERSIONS} mais recentes')

    to_delete = finalized[KEEP_VERSIONS:]
    if not to_delete:
        print('Nenhuma versão para deletar.')
        return

    deleted = 0
    for v in to_delete:
        name = v.get('name', '')
        try:
            status = delete_version(access_token, name)
            if status in (200, 204):
                deleted += 1
                print(f'  Deletado: {name.split("/")[-1]} ({status})')
            else:
                print(f'  Aviso: status {status} ao deletar {name.split("/")[-1]}')
        except Exception as e:
            print(f'  Erro ao deletar {name}: {e}')

    print(f'Cleanup concluído. Deletadas: {deleted}/{len(to_delete)} versões.')


if __name__ == '__main__':
    main()
