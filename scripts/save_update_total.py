#!/usr/bin/env python3
"""
Salva o total do faturamento do dia (fat_dia) e o timestamp do update
como GitHub Actions Variables, para uso no check_threshold do próximo run.

Variáveis salvas:
  LAST_UPDATE_TOTAL — soma do fat_dia de todas as lojas (float)
  LAST_UPDATE_TS    — timestamp ISO 8601 UTC do momento do update
"""
import os, sys, json, requests
from datetime import datetime, timezone

GH_PAT     = os.environ.get('GH_PAT', '').strip()
GH_REPO    = os.environ.get('GITHUB_REPOSITORY', '').strip()
TOTAL_FILE = os.environ.get('UPDATE_TOTAL_OUTPUT', '/tmp/update_total.txt')


def upsert_variable(name, value):
    """Cria ou atualiza uma GitHub Actions Variable."""
    headers = {
        'Authorization': f'token {GH_PAT}',
        'Accept':        'application/vnd.github.v3+json',
    }
    url_base = f'https://api.github.com/repos/{GH_REPO}/actions/variables/{name}'

    # Tentar atualizar (PATCH); se não existir, criar (POST)
    r = requests.patch(url_base, json={'name': name, 'value': str(value)},
                       headers=headers, timeout=15)
    if r.status_code == 404:
        url_post = f'https://api.github.com/repos/{GH_REPO}/actions/variables'
        r = requests.post(url_post, json={'name': name, 'value': str(value)},
                          headers=headers, timeout=15)
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')


def main():
    if not GH_PAT or not GH_REPO:
        print('GH_PAT ou GITHUB_REPOSITORY não definidos — skip')
        return

    # Ler total calculado pelo update_d360.py
    if not os.path.exists(TOTAL_FILE):
        print(f'Arquivo {TOTAL_FILE} não encontrado — skip')
        return

    with open(TOTAL_FILE) as f:
        total_str = f.read().strip()

    try:
        total = float(total_str)
    except ValueError:
        print(f'Valor inválido em {TOTAL_FILE}: {total_str!r} — skip')
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    print(f'Salvando LAST_UPDATE_TOTAL = R$ {total:,.2f}')
    upsert_variable('LAST_UPDATE_TOTAL', total)

    print(f'Salvando LAST_UPDATE_TS = {now_iso}')
    upsert_variable('LAST_UPDATE_TS', now_iso)

    print('Done.')


if __name__ == '__main__':
    main()
