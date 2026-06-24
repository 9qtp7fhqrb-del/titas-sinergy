#!/usr/bin/env python3
"""
Verifica se a atualização do D360 deve acontecer agora.

Regras:
  - Antes das 11h ou a partir das 20h (BRT): sempre atualiza
  - Entre 11h e 20h: só atualiza se o faturamento do dia cresceu >= R$10.000
    desde a última atualização, OU se houver flag manual no Firestore,
    OU se o workflow foi acionado manualmente (workflow_dispatch).

Saídas (GITHUB_OUTPUT):
  should_update = true | false
  skip_reason   = <texto descritivo>
"""

import os, sys, json
from datetime import datetime, timezone, timedelta

BRT = timezone(timedelta(hours=-3))
_now_brt = datetime.now(BRT)

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

ERP_BASE        = 'https://apicdc.casadocelular.com.br/api/v1'
FIREBASE_KEY    = 'AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8'
FIREBASE_PROJ   = 'titas-sinergy'
THRESHOLD       = float(os.environ.get('UPDATE_THRESHOLD', '10000'))
IS_MANUAL       = os.environ.get('IS_MANUAL', 'false').lower() == 'true'
LAST_TOTAL      = float(os.environ.get('LAST_UPDATE_TOTAL', '0') or '0')
LAST_TS         = os.environ.get('LAST_UPDATE_TS', '')
GH_OUTPUT_FILE  = os.environ.get('GITHUB_OUTPUT', '')

STORE_MAP = {
    'CDC BARREIRAS':              'barreiras',
    'CDC CARIACICA':              'cariacica',
    'CDC ITABUNA':                'itabuna',
    'CDC LINHARES':               'linhares',
    'CDC LARANJEIRAS':            'laranjeiras',
    'CDC MONTSERRAT':             'montserrat',
    'SHOPPING MOXUARA':           'moxuara',
    'CDC PRAIA DA COSTA':         'praiadacosta',
    'CDC SAO MATEUS':             'saomateus',
    'CDC SERRA':                  'serra',
    'CDC TEIXEIRA DE FREITAS NOVO': 'teixeira',
}


def gh_output(key, value):
    line = f'{key}={value}\n'
    if GH_OUTPUT_FILE:
        with open(GH_OUTPUT_FILE, 'a') as f:
            f.write(line)
    else:
        print(f'[OUTPUT] {line.strip()}')


# ── ERP ──────────────────────────────────────────────────────────────────────

def get_or_login_token():
    cached = os.environ.get('ERP_TOKEN_CACHE', '').strip()
    if cached:
        try:
            today = _now_brt.strftime('%Y-%m-%d')
            r = requests.get(f'{ERP_BASE}/reports/sales_by_collaborator',
                params={'start_date': today, 'end_date': today,
                        'report_view_mode': 'summary', 'show_insights': 'false',
                        'include_unassigned_residual': 'false'},
                headers={'Authorization': f'Bearer {cached}', 'Accept': 'application/json'},
                timeout=15)
            if r.status_code == 200:
                return cached, False
        except Exception:
            pass

    login = os.environ.get('ERP_LOGIN', '')
    pwd   = os.environ.get('ERP_PASSWORD', '')
    if not login or not pwd:
        raise ValueError('Credenciais ERP não encontradas')

    r = requests.post(f'{ERP_BASE}/login',
        json={'user': {'login': login, 'password': pwd}},
        timeout=30)
    r.raise_for_status()
    data = r.json()
    token = data.get('token') or (data.get('data') or {}).get('token')
    if not token:
        raise ValueError(f'Token ERP não encontrado. Chaves: {list(data.keys())}')
    return token, True


def get_today_total(token):
    today = _now_brt.strftime('%Y-%m-%d')
    r = requests.get(f'{ERP_BASE}/reports/sales_by_collaborator',
        params={'start_date': today, 'end_date': today,
                'report_view_mode': 'summary', 'show_insights': 'false',
                'include_unassigned_residual': 'false'},
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
        timeout=60)
    r.raise_for_status()
    data = r.json()

    collaborators = []
    if isinstance(data, list):
        collaborators = data
    elif isinstance(data.get('data'), dict):
        collaborators = data['data'].get('by_collaborator', [])
    else:
        for k in ('collaborators', 'results', 'report', 'sellers'):
            if isinstance(data.get(k), list):
                collaborators = data[k]
                break

    total = 0.0
    for c in collaborators:
        if c.get('profile_key') != 'seller':
            continue
        raw = (c.get('store_name') or '').upper().strip()
        if raw not in STORE_MAP:
            continue
        try:
            total += float(c.get('total_sold', 0) or 0)
        except Exception:
            pass
    return round(total, 2)


# ── Firestore flag ────────────────────────────────────────────────────────────

def check_manual_flag():
    """Retorna True se há um pedido manual de atualização recente no Firestore."""
    try:
        r = requests.get(
            f'https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJ}/databases/(default)/documents/ts_d360_config/manual_update_request',
            params={'key': FIREBASE_KEY},
            timeout=10)
        if r.status_code != 200:
            return False

        fields = r.json().get('fields', {})
        if not fields.get('forced', {}).get('booleanValue', False):
            return False

        ts_str = fields.get('ts', {}).get('timestampValue', '')
        if not ts_str:
            return False

        req_ts  = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        now_utc = datetime.now(timezone.utc)
        age_min = (now_utc - req_ts).total_seconds() / 60

        if age_min > 60:
            print(f'  Flag manual ignorada (muito antiga: {age_min:.0f} min)')
            return False

        if LAST_TS:
            try:
                last_dt = datetime.fromisoformat(LAST_TS.replace('Z', '+00:00'))
                if req_ts <= last_dt:
                    print(f'  Flag manual ignorada (anterior ao último update)')
                    return False
            except Exception:
                pass

        print(f'  ⚡ Flag manual detectada! ({age_min:.0f} min atrás)')
        return True

    except Exception as e:
        print(f'  Aviso ao verificar flag Firestore: {e}')
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    hour = _now_brt.hour
    print(f'check_threshold — {_now_brt.strftime("%H:%M")} BRT | IS_MANUAL={IS_MANUAL} | LAST_TOTAL=R${LAST_TOTAL:,.0f}')

    # 1. Dispatch manual → sempre atualiza
    if IS_MANUAL:
        gh_output('should_update', 'true')
        gh_output('skip_reason',   'dispatch_manual')
        print('✅ Dispatch manual — atualizando')
        return

    # 2. Fora da janela de threshold → sempre atualiza
    if hour < 11 or hour >= 20:
        gh_output('should_update', 'true')
        gh_output('skip_reason',   f'fora_da_janela_{hour}h')
        print(f'✅ Fora da janela ({hour}h BRT) — atualizando')
        return

    # 3. Após 17h o threshold cai para R$1.000 (vendas desaceleram no fim do dia)
    if hour >= 17:
        THRESHOLD_EFETIVO = 1000.0
    else:
        THRESHOLD_EFETIVO = THRESHOLD

    # 4. Dentro da janela 11h-20h: verificar flag manual e threshold
    print(f'Janela de threshold ativa ({hour}h BRT, threshold efetivo R${THRESHOLD_EFETIVO:,.0f}). Verificando flag Firestore e ERP...')

    if check_manual_flag():
        gh_output('should_update', 'true')
        gh_output('skip_reason',   'flag_manual_firestore')
        print('✅ Flag manual no Firestore — atualizando')
        return

    # Detectar virada de dia: se LAST_TS é de outro dia, base do threshold é 0
    last_total_base = LAST_TOTAL
    if LAST_TS:
        try:
            last_dt_brt = datetime.fromisoformat(LAST_TS.replace('Z', '+00:00')).astimezone(BRT)
            if last_dt_brt.date() < _now_brt.date():
                last_total_base = 0.0
                print(f'  ↺ Virada de dia detectada (último update: {last_dt_brt.strftime("%d/%m %H:%M")}) — base resetada para 0')
        except Exception:
            pass

    try:
        token, is_new = get_or_login_token()
        if is_new:
            out = os.environ.get('ERP_TOKEN_OUTPUT', '')
            if out:
                with open(out, 'w') as f:
                    f.write(token)
                print(f'  Token novo salvo em {out}')

        today_total = get_today_total(token)
        diff = today_total - last_total_base
        print(f'  Hoje: R$ {today_total:,.2f} | Base: R$ {last_total_base:,.2f} | Diff: R$ {diff:,.2f} | Threshold: R$ {THRESHOLD_EFETIVO:,.0f}')

        if diff < THRESHOLD_EFETIVO:
            gh_output('should_update', 'false')
            gh_output('skip_reason',   f'threshold_R${diff:.0f}_de_R${THRESHOLD_EFETIVO:.0f}')
            print(f'⏭️  Threshold não atingido — pulando (faltam R$ {THRESHOLD_EFETIVO - diff:,.0f})')
        else:
            gh_output('should_update', 'true')
            gh_output('skip_reason',   f'threshold_atingido_diff_R${diff:.0f}')
            print(f'✅ Threshold atingido (diff R$ {diff:,.0f}) — atualizando')

    except Exception as e:
        print(f'AVISO: erro ao verificar threshold ({e}) — prosseguindo com update por segurança')
        gh_output('should_update', 'true')
        gh_output('skip_reason',   f'erro_threshold_{e}')


if __name__ == '__main__':
    main()
