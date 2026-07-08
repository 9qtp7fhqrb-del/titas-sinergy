#!/usr/bin/env python3
"""
D360 Titãs Sinergy — Atualização automática via API ERP CDC
Atualiza por loja: total, acessorios.total, agendFat, agendamentos.total, agendamentos.top, fat_dia
"""
import re, os, sys
from datetime import date, datetime, timezone, timedelta

# Fuso horário de Brasília (BRT = UTC-3) — garante data correta no GitHub Actions (UTC)
BRT = timezone(timedelta(hours=-3))
_now_brt = datetime.now(BRT)

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

ERP_BASE      = 'https://apicdc.casadocelular.com.br/api/v1'
INDEX_HTML    = os.environ.get('INDEX_HTML', 'index.html')
FIREBASE_KEY  = 'AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8'
FIREBASE_PROJ = 'titas-sinergy'

FINANCEIRAS_GROUPS = [
    {'nm': 'PayJoy',    'ids': [8]},
    {'nm': 'OdresCred', 'ids': [9]},
    {'nm': 'Outras',    'ids': [72, 74, 12, 76]},
]

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

# Lojas de cada subrede (chaves do STORE_MAP)
SUBREDE_LOJAS = {
    't1': ['cariacica', 'itabuna', 'moxuara', 'praiadacosta'],
    't2': ['barreiras', 'teixeira', 'laranjeiras'],
    't3': ['saomateus', 'serra', 'montserrat', 'linhares'],
}

# ── API ──────────────────────────────────────────────────────────────────────

def erp_login(user, password, retries=4, wait=15):
    """Login com retry automático em caso de erro 5xx (servidor instável)."""
    import time
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(f'{ERP_BASE}/login',
                json={'user': {'login': user, 'password': password}},
                timeout=30)
            r.raise_for_status()
            data = r.json()
            token = data.get('token') or (data.get('data') or {}).get('token')
            if not token:
                raise ValueError(f"Token não encontrado. Chaves: {list(data.keys())}")
            return token
        except requests.exceptions.HTTPError as e:
            last_err = e
            if e.response is not None and e.response.status_code < 500:
                raise  # 4xx: não adianta retry
            print(f"  Login tentativa {attempt}/{retries} falhou ({e}). Aguardando {wait}s...")
            time.sleep(wait)
        except requests.exceptions.RequestException as e:
            last_err = e
            print(f"  Login tentativa {attempt}/{retries} falhou ({e}). Aguardando {wait}s...")
            time.sleep(wait)
    raise last_err

def erp_token_valid(token):
    """Verifica se o token ainda é válido sem fazer novo login."""
    try:
        today = date.today().strftime('%Y-%m-%d')
        r = requests.get(f'{ERP_BASE}/reports/sales_by_collaborator',
            params={'start_date': today, 'end_date': today,
                    'report_view_mode': 'summary', 'show_insights': 'false',
                    'include_unassigned_residual': 'false'},
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
            timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def get_or_refresh_token(user, password):
    """Reutiliza token cacheado se ainda válido; caso contrário faz novo login."""
    cached = os.environ.get('ERP_TOKEN_CACHE', '').strip()
    if cached:
        print("Verificando token cacheado...")
        if erp_token_valid(cached):
            print("Token cacheado ainda válido — sem novo login")
            return cached, False   # (token, is_new)
        print("Token expirado, fazendo novo login...")
    else:
        print("Sem token cacheado, fazendo login...")
    token = erp_login(user, password)
    return token, True   # (token, is_new)

def save_erp_token_to_firestore(token):
    """Salva o token ERP no Firestore para uso direto pelo browser (botão de atualização)."""
    try:
        import time as _time
        saved_at = int(_time.time() * 1000)  # ms desde epoch
        url = (f'https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJ}'
               f'/databases/(default)/documents/ts_d360_config/erp_session?key={FIREBASE_KEY}')
        payload = {'fields': {
            'token':   {'stringValue': token},
            'savedAt': {'integerValue': str(saved_at)},
        }}
        r = requests.patch(url, json=payload, timeout=15)
        if r.status_code in (200, 201):
            print('  Token ERP salvo no Firestore (disponível para atualização direta pelo browser)')
        else:
            print(f'  AVISO: erro ao salvar token ERP no Firestore: {r.status_code}')
    except Exception as e:
        print(f'  AVISO: erro ao salvar token ERP no Firestore: {e}')


def save_d360_to_firestore(sales, acess, acess_dia, today_sellers_proc, fin, fin_acum, agend):
    """Atualiza ts_d360/dados_360_atual no Firestore — dispara onSnapshot em todos os browsers abertos."""
    import time, calendar
    MESES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    periodo = f"{MESES[_now_brt.month - 1]} {_now_brt.year}"
    dias_mes = calendar.monthrange(_now_brt.year, _now_brt.month)[1]
    dias_decorridos = min(_now_brt.day, dias_mes)

    lojas_data = {}
    for sk in STORE_MAP.values():
        lojas_data[sk] = {
            'total':         round(sales.get(sk, {}).get('total', 0), 2),
            'fat_dia':       round(today_sellers_proc.get(sk, {}).get('total', 0), 2),
            'top_dia':       today_sellers_proc.get(sk, {}).get('top', []),
            'acess_dia':     round(acess_dia.get(sk, {}).get('total', 0), 2),
            'acess_dia_top': acess_dia.get(sk, {}).get('top', []),
            'fin_dia':       round(fin.get(sk, {}).get('total', 0), 2),
            'fin_mes':       round(fin_acum.get(sk, {}).get('total', 0), 2),
            'agendFat':      round(agend.get(sk, {}).get('total', 0), 2),
            'acessorios':    {
                'total': round(acess.get(sk, {}).get('total', 0), 2),
                'top':   acess.get(sk, {}).get('top', []),
            },
        }

    snap = {
        'lojas':          lojas_data,
        'diasDecorridos': dias_decorridos,
        'periodo':        periodo,
        'savedAt':        int(time.time() * 1000),
    }

    def to_fs(v):
        if v is None:            return {'nullValue': None}
        if isinstance(v, bool):  return {'booleanValue': v}
        if isinstance(v, int):   return {'integerValue': str(v)}
        if isinstance(v, float): return {'doubleValue': v}
        if isinstance(v, list):  return {'arrayValue': {'values': [to_fs(i) for i in v]}}
        if isinstance(v, dict):  return {'mapValue': {'fields': {k2: to_fs(v2) for k2, v2 in v.items()}}}
        return {'stringValue': str(v)}

    fields = {k: to_fs(v) for k, v in snap.items()}
    url = (f'https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJ}'
           f'/databases/(default)/documents/ts_d360/dados_360_atual?key={FIREBASE_KEY}')
    try:
        r = requests.patch(url, json={'fields': fields}, timeout=20)
        if r.status_code in (200, 201):
            print(f'  ✅ Firestore atualizado — onSnapshot acionado em todos os browsers abertos')
        else:
            print(f'  AVISO: Firestore retornou {r.status_code}: {r.text[:200]}')
    except Exception as e:
        print(f'  AVISO: erro ao atualizar Firestore: {e}')


def fetch_sales(token, start, end, channel_id=None, retries=4, wait=15):
    import time
    params = {
        'start_date': start,
        'end_date': end,
        'include_unassigned_residual': 'false',
        'show_insights': 'false',
        'report_view_mode': 'summary',
    }
    if channel_id:
        params['channel_ids[]'] = channel_id
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(f'{ERP_BASE}/reports/sales_by_collaborator',
                params=params,
                headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
                timeout=60)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            last_err = e
            if e.response is not None and e.response.status_code < 500:
                raise
            print(f"  fetch_sales tentativa {attempt}/{retries} falhou ({e}). Aguardando {wait}s...")
            time.sleep(wait)
        except requests.exceptions.RequestException as e:
            last_err = e
            print(f"  fetch_sales tentativa {attempt}/{retries} falhou ({e}). Aguardando {wait}s...")
            time.sleep(wait)
    raise last_err

def fetch_financeiras_ids(token, retries=3, wait=10):
    """Busca IDs de todos os meios de pagamento do tipo Financeira (modality=finance_company)."""
    import time
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(f'{ERP_BASE}/payment_methods',
                headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
                timeout=20)
            r.raise_for_status()
            pms = r.json().get('payment_methods', [])
            ids = [pm['id'] for pm in pms
                   if pm.get('active') and (pm.get('modality') or {}).get('key') == 'finance_company']
            return ids
        except Exception as e:
            if attempt < retries:
                time.sleep(wait)
            else:
                print(f"  AVISO: falha ao buscar IDs financeiras ({e}), usando padrão [8,9]")
                return [8, 9]  # OdresCred, PayJoy — fallback

def fetch_store_ids(token, retries=3, wait=10):
    """
    Busca lista de lojas do ERP e retorna mapa {store_key: store_id}.
    Tenta /stores, /locations e /units — retorna {} se nenhum funcionar.
    """
    import time
    endpoints = ['/stores', '/locations', '/units', '/branches']
    for ep in endpoints:
        for attempt in range(1, retries + 1):
            try:
                r = requests.get(f'{ERP_BASE}{ep}',
                    headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
                    timeout=20)
                if r.status_code == 404:
                    break  # endpoint não existe, tentar próximo
                r.raise_for_status()
                data = r.json()
                # Normalizar: pode vir em data.stores, data.locations, data[] etc.
                items = []
                if isinstance(data, list):
                    items = data
                else:
                    for k in ('stores', 'locations', 'units', 'branches', 'data'):
                        if isinstance(data.get(k), list):
                            items = data[k]
                            break
                if not items:
                    break
                # Montar mapa nome_upper → id
                id_map = {}
                for item in items:
                    name = (item.get('name') or item.get('store_name') or item.get('label') or '').upper().strip()
                    sid  = item.get('id') or item.get('store_id')
                    if name and sid:
                        key = STORE_MAP.get(name)
                        if key:
                            id_map[key] = sid
                if id_map:
                    print(f"  IDs de lojas encontrados via {ep}: {id_map}")
                    return id_map
                break
            except Exception as e:
                if attempt < retries:
                    time.sleep(wait)
    print("  AVISO: IDs de lojas não encontrados — gerencial por subrede indisponível")
    return {}


def fetch_gerencial(token, start, end, payment_method_ids=None, store_ids=None, retries=4, wait=15):
    """Busca relatório gerencial, opcionalmente filtrado por meios de pagamento e/ou lojas."""
    import time
    params = {'start_date': start, 'end_date': end}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            # Monta query string manual para suportar arrays (payment_method_ids[] e store_ids[])
            qs_parts = []
            if payment_method_ids:
                qs_parts += [f'payment_method_ids[]={i}' for i in payment_method_ids]
            if store_ids:
                qs_parts += [f'store_ids[]={i}' for i in store_ids]
            if qs_parts:
                url = f'{ERP_BASE}/reports/gerencial?' + '&'.join(qs_parts)
            else:
                url = f'{ERP_BASE}/reports/gerencial'
            r = requests.get(url,
                params=params,
                headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
                timeout=60)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            last_err = e
            if e.response is not None and e.response.status_code < 500:
                raise
            print(f"  fetch_gerencial tentativa {attempt}/{retries} falhou ({e}). Aguardando {wait}s...")
            time.sleep(wait)
        except requests.exceptions.RequestException as e:
            last_err = e
            print(f"  fetch_gerencial tentativa {attempt}/{retries} falhou ({e}). Aguardando {wait}s...")
            time.sleep(wait)
    raise last_err

def _parse_brl(val):
    """Parseia string monetária BR (ex: 'R$  73.666,00') para float."""
    try:
        s = str(val).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.').replace('%', '').strip()
        return float(s)
    except Exception:
        return None


def _parse_margem_pct(val):
    """Converte valor de margem (float, '45,47%', 'R$...', 0-1 decimal) para percentual."""
    v = _parse_brl(val)
    if v is None:
        return None
    if 0 < v <= 1:
        v = round(v * 100, 2)
    if 0 < v < 100:
        return round(v, 2)
    return None


def _extract_from_dict(d):
    """Tenta extrair margem bruta de um dicionário plano."""
    candidates = [
        'gross_margin', 'margem_bruta', 'gross_margin_percentage',
        'gross_profit_margin', 'margin', 'brute_margin',
    ]
    for key in candidates:
        val = d.get(key)
        if val is not None:
            v = _parse_margem_pct(val)
            if v:
                return v
    # Calcular de receita bruta + lucro bruto
    rev_keys    = ['gross_revenue', 'receita_bruta', 'total_revenue', 'revenue', 'net_revenue']
    profit_keys = ['gross_profit', 'lucro_bruto', 'brute_profit', 'profit', 'gross_profit_value']
    try:
        rev = next((_parse_brl(d[k]) for k in rev_keys if d.get(k)), None)
        prf = next((_parse_brl(d[k]) for k in profit_keys if d.get(k)), None)
        if rev and prf and rev > 0:
            return round(prf / rev * 100, 2)
    except Exception:
        pass
    # Calcular de receita - custo
    try:
        rev  = next((_parse_brl(d[k]) for k in rev_keys if d.get(k)), None)
        cost_keys = ['total_costs', 'cost', 'custo', 'total_cost', 'cost_of_goods', 'cogs']
        cost = next((_parse_brl(d[k]) for k in cost_keys if d.get(k)), None)
        if rev and cost and rev > 0:
            return round((rev - cost) / rev * 100, 2)
    except Exception:
        pass
    return None


def _deep_search_margem(obj, depth=0, skip_keys=('trends', 'metadata', 'employee_ranking', 'list', 'by_payment_method', 'by_brand')):
    """Busca recursiva de margem bruta em qualquer nível do objeto."""
    if depth > 3 or not isinstance(obj, dict):
        return None
    v = _extract_from_dict(obj)
    if v:
        return v
    for key, val in obj.items():
        if key in skip_keys:
            continue
        if isinstance(val, dict):
            v = _deep_search_margem(val, depth + 1, skip_keys)
            if v:
                return v
    return None


def extract_margem_bruta(data):
    """
    Extrai a Margem Bruta (%) do relatório gerencial da API CDC.
    Estrutura real: {summary:{financial_overview:{gross_margin:'45,47%',...},...}, revenue_breakdown:{...}, cost_breakdown:{...}}
    Faz busca profunda para lidar com mudanças de estrutura. Retorna float (ex: 45.47) ou None.
    """
    if not data:
        return None

    # 1. Busca profunda em summary.financial_overview (caminho confirmado da API CDC)
    try:
        fo = data['summary']['financial_overview']
        v = _extract_from_dict(fo)
        if v:
            return v
    except Exception:
        pass

    # 2. Calcular de revenue_breakdown e cost_breakdown (nível raiz)
    try:
        rb = data.get('revenue_breakdown') or {}
        cb = data.get('cost_breakdown') or {}
        rev  = _parse_brl(rb.get('total_revenue') or rb.get('gross_revenue') or rb.get('total') or 0)
        cost = _parse_brl(cb.get('total_costs') or cb.get('total_cost') or cb.get('total') or 0)
        if rev and cost and rev > 0:
            return round((rev - cost) / rev * 100, 2)
    except Exception:
        pass

    # 3. Busca profunda em toda a estrutura
    v = _deep_search_margem(data)
    if v:
        return v

    print(f"  AVISO: margem_bruta não encontrada. Chaves da API: {list(data.keys())[:20]}")
    if isinstance(data.get('summary'), dict):
        print(f"  Chaves de summary: {list(data['summary'].keys())[:20]}")
    return None


def update_margem_dia(content, margem):
    """Atualiza margem_dia (margem bruta do dia) no index.html."""
    new_val = f'{margem:.2f}'
    updated = re.sub(r'(\bmargem_dia:\s*)\d+(?:\.\d+)?(?=\s*,)', f'\\g<1>{new_val}', content, count=1)
    if updated == content:
        print(f"  AVISO: campo margem_dia não encontrado no HTML")
    return updated


def update_margem_dia_subredes(content, margens):
    """Atualiza margem_dia_subredes no index.html. margens: {'t1': 44.77, ...}"""
    for sub, val in margens.items():
        if val is None: continue
        pattern = rf'(margem_dia_subredes\s*:\s*\{{[^}}]*\b{sub}\s*:\s*)\d+(?:\.\d+)?'
        new_content = re.sub(pattern, f'\\g<1>{val:.2f}', content, count=1)
        if new_content != content:
            print(f"  margem_dia_subredes.{sub} → {val:.2f}%")
            content = new_content
        else:
            print(f"  AVISO: margem_dia_subredes.{sub} não encontrado")
    return content


def update_dias_decorridos(content, dias_decorridos, dias_mes, start_str, today_str):
    """Atualiza diasDecorridos, diasMes e comentário de fonte no D360 do index.html."""
    # diasDecorridos — substitui expressão dinâmica OU número anterior pelo valor correto
    def _repl_dias(m):
        prefix = m.group(1) if m.group(1) else m.group(2)
        return prefix + str(dias_decorridos)
    updated = re.sub(
        r'(diasDecorridos\s*:\s*)Math\.min\(new Date\(\)\.getDate\(\),\s*\d+\)'
        r'|(diasDecorridos\s*:\s*)\d+',
        _repl_dias, content, count=1
    )
    if updated == content:
        print(f"  AVISO: campo diasDecorridos não encontrado no HTML")
    else:
        content = updated
    # diasMes
    updated2 = re.sub(r'(diasMes\s*:\s*)\d+(?=\s*,)', f'\\g<1>{dias_mes}', content, count=1)
    if updated2 != content:
        content = updated2
    # Comentário de fonte — mantém rastreabilidade do período dos dados
    novo_com = f'// ── Totais acumulados {start_str} a {today_str} · Atualizado automaticamente ──'
    content = re.sub(
        r'// ── Totais acumulados [^\n]+\n',
        novo_com + '\n',
        content, count=1
    )
    return content


def update_margem_rede(content, margem):
    """Atualiza margem_mes na rede (D360 top-level) no index.html."""
    new_val = f'{margem:.2f}'
    updated = re.sub(r'(\bmargem_mes:\s*)\d+(?:\.\d+)?(?=\s*,)', f'\\g<1>{new_val}', content, count=1)
    if updated == content:
        print(f"  AVISO: campo margem_mes não encontrado no HTML")
    return updated


def update_margem_subredes(content, margens):
    """
    Atualiza margem_subredes no index.html.
    margens: {'t1': 45.17, 't2': 44.20, 't3': 43.80}
    Substitui apenas subredes com dados novos (>0).
    """
    for sub, val in margens.items():
        if not val:
            continue
        # Encontra a chave no objeto margem_subredes: { t1: X, t2: X, t3: X }
        pattern = rf'(margem_subredes\s*:\s*\{{[^}}]*\b{sub}\s*:\s*)\d+(?:\.\d+)?'
        new = f'\\g<1>{val:.2f}'
        updated = re.sub(pattern, new, content, count=1)
        if updated != content:
            content = updated
            print(f"  margem_subredes.{sub} → {val:.2f}%")
        else:
            print(f"  AVISO: margem_subredes.{sub} não encontrado no HTML")
    return content


def process_gerencial(data):
    """
    Processa employee_ranking do relatório gerencial.
    Inclui apenas profile_name == 'Vendedor'.
    Retorna: {store_key: {'total': float, 'top': [{'n','i','t'}]}}
    """
    def parse_brl(s):
        try:
            return float(str(s).replace('R$', '').replace('.', '').replace(',', '.').strip())
        except Exception:
            return 0.0

    ranking = (data or {}).get('employee_ranking', [])
    stores = {}
    for emp in ranking:
        if (emp.get('profile_name') or '').strip().lower() != 'vendedor':
            continue
        raw_name = (emp.get('store_name') or '').upper().strip()
        store_key = STORE_MAP.get(raw_name)
        if not store_key:
            continue
        val = parse_brl(emp.get('total_sales', 0))
        if val <= 0:
            continue
        if store_key not in stores:
            stores[store_key] = {'total': 0.0, 'top': []}
        stores[store_key]['total'] += val
        name = (emp.get('name') or '').strip()
        parts = name.split()
        initials = (parts[0][0] + parts[1][0]).upper() if len(parts) >= 2 else name[:2].upper()
        stores[store_key]['top'].append({'n': name, 'i': initials, 't': val})
    for s in stores.values():
        s['top'].sort(key=lambda x: x['t'], reverse=True)
        s['total'] = round(s['total'], 2)
    return stores


def get_collaborators(data):
    if isinstance(data, list):
        return data
    # Estrutura correta da API CDC: data['data']['by_collaborator']
    if 'data' in data and isinstance(data['data'], dict):
        by_col = data['data'].get('by_collaborator')
        if isinstance(by_col, list):
            return by_col
    for key in ('collaborators', 'results', 'report', 'sellers'):
        if key in data and isinstance(data[key], list):
            return data[key]
    return []

# ── Processamento ─────────────────────────────────────────────────────────────

def process(data, value_fn):
    """
    Filtra sellers, agrega por loja.
    Retorna: {store_key: {'total': float, 'top': [{'n','i','t'}]}}
    """
    stores = {}
    for c in get_collaborators(data):
        if c.get('profile_key') != 'seller':
            continue
        raw_name = (c.get('store_name') or '').upper().strip()
        store_key = STORE_MAP.get(raw_name)
        if not store_key:
            continue
        val = value_fn(c) or 0
        if val <= 0:
            continue
        if store_key not in stores:
            stores[store_key] = {'total': 0, 'top': []}
        stores[store_key]['total'] += val
        name = (c.get('collaborator_name') or '').strip()
        parts = name.split()
        initials = (parts[0][0] + parts[1][0]).upper() if len(parts) >= 2 else name[:2].upper()
        stores[store_key]['top'].append({'n': name, 'i': initials, 't': val, 'p': c.get('sales_count', 0)})

    for s in stores.values():
        s['top'].sort(key=lambda x: x['t'], reverse=True)
        s['total'] = round(s['total'], 2)

    return stores

# ── Atualização do HTML ───────────────────────────────────────────────────────

def find_section(content, store_key):
    """Retorna (start, end) da seção do store no HTML.
    Busca especificamente a linha que inicia o objeto da loja: '        key:   { label:'
    Ignora ocorrências em margem_lojas (que têm apenas um número, ex: 'key: 0,').
    """
    import re as _re
    # Padrão: newline + 8 espaços + chave + : + espaços* + { (início de objeto)
    pattern = f'\n        {store_key}:\\s*\\{{'
    m = _re.search(pattern, content)
    if not m:
        return None, None
    start = m.start()
    # Limite superior: fechamento do objeto D360 (\n    }\n};) — evita que a última
    # loja (praiadacosta) tenha seção que abranja o restante do arquivo
    d360_close = _re.search(r'\n    \}\n\};', content[start:])
    end = (start + d360_close.end()) if d360_close else len(content)
    for sk in STORE_MAP.values():
        if sk == store_key:
            continue
        m2 = _re.search(f'\n        {sk}:\\s*\\{{', content[start + 1:end])
        if m2:
            pos = start + 1 + m2.start()
            if 0 < pos < end:
                end = pos
    return start, end

def fmt_fin_bd(bd_list):
    items = [f"{{nm:'{e['nm']}',t:{e['t']}}}" for e in bd_list]
    return '[' + ','.join(items) + ']'

def fmt_top_with_bd(top_list):
    items = []
    for e in top_list:
        bd_items = ','.join(f"{{nm:'{b['nm']}',t:{b['t']}}}" for b in (e.get('bd') or []))
        items.append(f"{{n:'{e['n']}',i:'{e['i']}',t:{e['t']},bd:[{bd_items}]}}")
    return '[' + ','.join(items) + ']'

def fmt_top(top_list):
    items = [f"{{n:'{e['n']}',i:'{e['i']}',t:{e['t']}}}" for e in top_list]
    return '[' + ', '.join(items) + ']'

def update_store(content, store_key, total, acess_total, agend_total, agend_top, fat_dia=0, top_dia=None, acess_dia=0, acess_dia_top=None, fin_dia=0, top_fin=None, fin_mes=0, top_fin_mes=None, fin_bd=None, sellers_top=None, sellers_today=None):
    start, end = find_section(content, store_key)
    if start is None:
        print(f"  AVISO: seção '{store_key}' não encontrada no HTML")
        return content

    sec = content[start:end]

    # 1. total (na linha principal da loja)
    sec = re.sub(r'(\btotal:)\d+(?:\.\d+)?(?=\s*,\s*ped:)', f'\\g<1>{total}', sec, count=1)

    # 2. agendFat
    sec = re.sub(r'\bagendFat:\d+(?:\.\d+)?', f'agendFat:{agend_total}', sec, count=1)

    # 2b. fat_dia (faturamento do dia vigente)
    sec = re.sub(r'\bfat_dia:\d+(?:\.\d+)?', f'fat_dia:{fat_dia}', sec, count=1)

    # 2b2. acess_dia (acessórios do dia — total)
    if re.search(r'\bacess_dia:\d+(?:\.\d+)?', sec):
        sec = re.sub(r'\bacess_dia:\d+(?:\.\d+)?', f'acess_dia:{acess_dia}', sec, count=1)
    else:
        sec = re.sub(r'(\bfat_dia:\d+(?:\.\d+)?)', f'\\g<1>, acess_dia:{acess_dia}', sec, count=1)

    # 2b3. acess_dia_top (ranking vendedores acessórios do dia)
    if acess_dia_top is not None:
        top_str = fmt_top(acess_dia_top)
        if re.search(r'acess_dia_top:\[', sec):
            sec = re.sub(r'acess_dia_top:\[[^\]]*\]', f'acess_dia_top:{top_str}', sec, count=1)
        else:
            sec = re.sub(r'(\bacess_dia:\d+(?:\.\d+)?)', f'\\g<1>, acess_dia_top:{top_str}', sec, count=1)

    # 2c. top_dia (vendedores do dia)
    if top_dia is not None:
        top_dia_str = fmt_top(top_dia)
        sec, n_td = re.subn(r'top_dia:\[[^\]]*\]', f'top_dia:{top_dia_str}', sec, count=1)

    # 2d. fin_dia (financeiras do dia)
    sec = re.sub(r'\bfin_dia:\d+(?:\.\d+)?', f'fin_dia:{fin_dia}', sec, count=1)

    # 2e. top_fin (vendedores financeiras do dia)
    if top_fin is not None:
        top_fin_str = fmt_top(top_fin)
        sec = re.sub(r'top_fin:\[[^\]]*\]', f'top_fin:{top_fin_str}', sec, count=1)

    # 2f. fin_mes (financeiras acumulado mensal)
    sec = re.sub(r'\bfin_mes:\d+(?:\.\d+)?', f'fin_mes:{fin_mes}', sec, count=1)

    # 2g. top_fin_mes (vendedores financeiras mensais com bd)
    if top_fin_mes is not None:
        top_fin_mes_str = fmt_top_with_bd(top_fin_mes)
        sec = re.sub(r'top_fin_mes:\[(?:[^\[\]]|\[[^\[\]]*\])*\]', f'top_fin_mes:{top_fin_mes_str}', sec, count=1)

    # 2h. fin_bd (breakdown por financeira)
    if fin_bd is not None:
        fin_bd_str = fmt_fin_bd(fin_bd)
        if 'fin_bd:' in sec:
            sec = re.sub(r'fin_bd:\[[^\]]*\]', f'fin_bd:{fin_bd_str}', sec, count=1)
        else:
            # Inserir após top_fin_mes se o campo ainda não existe
            sec = re.sub(r'(top_fin_mes:\[(?:[^\[\]]|\[[^\[\]]*\])*\])', f'\\1, fin_bd:{fin_bd_str}', sec, count=1)

    # 3. acessorios.total
    sec = re.sub(r'(\bacessorios:\{total:)\d+(?:\.\d+)?', f'\\g<1>{acess_total}', sec, count=1)

    # 4. agendamentos (single-line)
    top_str = fmt_top(agend_top)
    new_agend = f'agendamentos:{{total:{agend_total}, top:{top_str}}}'
    sec, n = re.subn(
        r'agendamentos:\{total:\d+(?:\.\d+)?,\s*top:\[[^\]]*\]\}',
        new_agend, sec, count=1
    )
    # 4b. agendamentos (multi-line)
    if n == 0:
        sec = re.sub(
            r'agendamentos:\{total:\d+(?:\.\d+)?,\s*top:\[[\s\S]*?\]\}',
            new_agend, sec, count=1
        )

    # 5. top[] de vendedores (o ÚLTIMO top:[] da seção = top principal, não agendamentos/acessorios)
    # sellers_top=None  → não tocar no top
    # sellers_top=[]    → zerar (ex: dia 1 do mês sem vendedores no salão)
    # sellers_top=[...] → atualizar normalmente
    if sellers_top is not None:
        all_tops_new = list(re.finditer(r'\btop:\[[\s\S]*?\](?=\s*[\}\]])', sec))
        if sellers_top:
            # Preservar ds e ult do top[] PRINCIPAL (último na seção)
            ds_ult = {}
            all_tops = list(re.finditer(r'\btop:\[([\s\S]*?)\](?=\s*[\}\]])', sec))
            if all_tops:
                # O top principal é o último que contém ds: (campo exclusivo do top de vendas)
                main_top_match = None
                for m in reversed(all_tops):
                    if 'ds:' in m.group(0) or (',p:' in m.group(0) and 'ult:' in m.group(0)):
                        main_top_match = m
                        break
                # Fallback: usar o último top[]
                if not main_top_match:
                    main_top_match = all_tops[-1]
                for item in re.finditer(r"\{[^}]*\bn:'([^']+)'[^}]*\}", main_top_match.group(0)):
                    txt = item.group(0)
                    nm  = re.search(r"n:'([^']+)'", txt)
                    ds  = re.search(r"ds:(\d+)", txt)
                    ult = re.search(r"ult:'([^']+)'", txt)
                    if nm:
                        key = nm.group(1).lower()
                        ds_ult[key] = {
                            'ds':  int(ds.group(1)) if ds else 0,
                            'ult': ult.group(1) if ult else ''
                        }
            # Data de hoje em formato dd/mm (para atualizar ult dos que venderam hoje)
            from datetime import date as _date
            today_fmt = _date.today().strftime('%d/%m')

            # Construir novo top[]
            top_items = []
            for v in sellers_top:
                nm_key = v['n'].lower()
                preserved = ds_ult.get(nm_key, {})
                old_ult = preserved.get('ult', '')
                ds_val  = preserved.get('ds', 0)

                # Se o vendedor vendeu hoje, atualiza ult e incrementa ds
                vendeu_hoje = sellers_today and nm_key in sellers_today
                if vendeu_hoje:
                    ult_val = today_fmt
                    if old_ult != today_fmt:   # dia novo → +1 dia ativo
                        ds_val = ds_val + 1
                else:
                    ult_val = old_ult

                item = f"{{n:'{v['n']}',i:'{v['i']}',p:{v['p']},t:{v['t']}"
                if ds_val:   item += f",ds:{ds_val}"
                if ult_val:  item += f",ult:'{ult_val}'"
                item += '}'
                top_items.append(item)
            new_top = 'top:[' + ',\n                '.join(top_items) + ']'
        else:
            # sellers_top=[] → zerar top acumulado (evita stale do mês anterior)
            new_top = 'top:[]'

        if all_tops_new:
            last = all_tops_new[-1]
            sec = sec[:last.start()] + new_top + sec[last.end():]

    # 6. ped = soma dos p dos sellers
    if sellers_top:
        new_ped = sum(v.get('p', 0) for v in sellers_top)
        if new_ped > 0:
            sec = re.sub(r'\bped:\d+', f'ped:{new_ped}', sec, count=1)

    return content[:start] + sec + content[end:]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    erp_user     = os.environ.get('ERP_LOGIN', '')
    erp_password = os.environ.get('ERP_PASSWORD', '')

    # Fallback: ler do arquivo de credenciais local
    if not erp_user or not erp_password:
        cred_path = os.path.expanduser('~/Documents/D360-Vendas/.erp-credentials.json')
        if os.path.exists(cred_path):
            import json
            creds = json.load(open(cred_path))
            erp_user     = creds.get('login', '')
            erp_password = creds.get('password', '')

    if not erp_user or not erp_password:
        print("ERRO: credenciais do ERP não encontradas")
        sys.exit(1)

    token, is_new_token = get_or_refresh_token(erp_user, erp_password)
    print("Token OK")

    # Salva token no Firestore para uso direto pelo browser (botão de atualização imediata)
    save_erp_token_to_firestore(token)

    # Se gerou token novo, salva para o workflow persistir no cache
    if is_new_token:
        token_out = os.environ.get('ERP_TOKEN_OUTPUT', '')
        if token_out:
            with open(token_out, 'w') as f:
                f.write(token)
            print(f"Token salvo em {token_out}")

    import calendar as _cal_main2
    today = _now_brt.strftime('%Y-%m-%d')
    start = _now_brt.strftime('%Y-%m-01')
    dias_decorridos = min(_now_brt.day, _cal_main2.monthrange(_now_brt.year, _now_brt.month)[1])
    print(f"Período: {start} → {today} (BRT {_now_brt.strftime('%H:%M')}, dia {dias_decorridos})")

    print("Buscando vendas gerais (acumulado)...")
    sales_data = fetch_sales(token, start, today)

    print("Buscando vendas do dia...")
    today_data = fetch_sales(token, today, today)

    print("Buscando Central de Agendamentos (canal 6)...")
    agend_data = fetch_sales(token, start, today, channel_id=6)

    print("Buscando IDs de financeiras...")
    fin_pm_ids = fetch_financeiras_ids(token)
    print(f"  IDs encontrados: {fin_pm_ids}")

    print("Buscando financeiras do dia...")
    fin_today_data = fetch_gerencial(token, today, today, payment_method_ids=fin_pm_ids)

    print("Buscando financeiras do mês...")
    fin_mes_data = fetch_gerencial(token, start, today, payment_method_ids=fin_pm_ids)

    print("Buscando IDs de lojas (para filtro gerencial por subrede)...")
    store_id_map = fetch_store_ids(token)

    print("Buscando Relatório Gerencial (margem bruta dia)...")
    gerencial_dia = fetch_gerencial(token, today, today)
    margem_dia = extract_margem_bruta(gerencial_dia)
    if margem_dia is not None:
        print(f"  Margem Bruta dia: {margem_dia:.2f}%")
    else:
        print("  AVISO: margem_dia não extraída")

    print("Buscando Relatório Gerencial (margem bruta rede)...")
    gerencial_rede = fetch_gerencial(token, start, today)
    margem_rede = extract_margem_bruta(gerencial_rede)
    if margem_rede is not None:
        print(f"  Margem Bruta rede: {margem_rede:.2f}%")
    else:
        print("  AVISO: margem_bruta não extraída — campo não será atualizado")

    print("Buscando margem bruta por subrede (mês e dia)...")
    margem_subredes = {}
    margem_dia_subredes = {}
    if store_id_map:
        for sub, lojas in SUBREDE_LOJAS.items():
            ids = [store_id_map[lk] for lk in lojas if lk in store_id_map]
            if ids:
                try:
                    g = fetch_gerencial(token, start, today, store_ids=ids)
                    m = extract_margem_bruta(g)
                    if m:
                        margem_subredes[sub] = m
                        print(f"  Margem mês {sub}: {m:.2f}%")
                except Exception as e:
                    print(f"  AVISO: erro ao buscar margem mês {sub}: {e}")
                try:
                    g_dia = fetch_gerencial(token, today, today, store_ids=ids)
                    m_dia = extract_margem_bruta(g_dia)
                    if m_dia:
                        margem_dia_subredes[sub] = m_dia
                        print(f"  Margem dia  {sub}: {m_dia:.2f}%")
                except Exception as e:
                    print(f"  AVISO: erro ao buscar margem dia {sub}: {e}")
    else:
        print("  IDs de lojas não disponíveis — margem_subredes não será atualizada automaticamente")

    print("Buscando breakdown por grupo de financeiras...")
    fin_groups_data = {}
    for grp in FINANCEIRAS_GROUPS:
        fin_groups_data[grp['nm']] = fetch_gerencial(token, start, today, payment_method_ids=grp['ids'])

    sales     = process(sales_data, lambda c: c.get('total_sold', 0))
    acess     = process(sales_data, lambda c: (c.get('group_totals') or {}).get('ACESSÓRIOS', 0))
    acess_dia = process(today_data, lambda c: (c.get('group_totals') or {}).get('ACESSÓRIOS', 0))
    agend     = process(agend_data, lambda c: (c.get('group_totals') or {}).get('SBON', 0))
    fin      = process_gerencial(fin_today_data)
    fin_acum = process_gerencial(fin_mes_data)
    fin_grps = {nm: process_gerencial(d) for nm, d in fin_groups_data.items()}

    # Vendas do dia: totais por loja e set de vendedores
    today_sellers_proc = process(today_data, lambda c: c.get('total_sold', 0))
    sellers_today_by_store = {}
    for sk, sv in today_sellers_proc.items():
        sellers_today_by_store[sk] = {v['n'].lower() for v in sv['top']}
    vendas_hoje_total = sum(len(v) for v in sellers_today_by_store.values())
    print(f"Vendedores com venda hoje: {vendas_hoje_total}")

    print("\nTotais por loja:")
    for sk in STORE_MAP.values():
        s  = sales.get(sk, {}).get('total', 0)
        a  = acess.get(sk, {}).get('total', 0)
        ag = agend.get(sk, {}).get('total', 0)
        fd = today_sellers_proc.get(sk, {}).get('total', 0)
        fn = fin.get(sk, {}).get('total', 0)
        fm = fin_acum.get(sk, {}).get('total', 0)
        print(f"  {sk:<15} total={s:>10,.2f} | acess={a:>8,.2f} | agend={ag:>10,.2f} | fat_dia={fd:>8,.2f} | fin_dia={fn:>8,.2f} | fin_mes={fm:>8,.2f}")

    # Montar fin_bd por loja e bd por vendedor
    fin_bd_by_store = {}
    top_fin_mes_bd_by_store = {}
    for sk in STORE_MAP.values():
        bd_store = []
        ven_fin = {}   # {nome_lower: {nm: valor}}
        for grp in FINANCEIRAS_GROUPS:
            nm = grp['nm']
            gdata = fin_grps.get(nm, {}).get(sk, {})
            gt = round(gdata.get('total', 0), 2)
            bd_store.append({'nm': nm, 't': gt})
            for v in gdata.get('top', []):
                k = v['n'].lower()
                if k not in ven_fin: ven_fin[k] = {'n': v['n'], 'i': v['i'], 'total': 0, 'bd': {}}
                ven_fin[k]['bd'][nm] = v['t']
                ven_fin[k]['total'] += v['t']
        fin_bd_by_store[sk] = bd_store
        # top_fin_mes com bd
        base_top = fin_acum.get(sk, {}).get('top', [])
        merged = []
        for v in base_top:
            k = v['n'].lower()
            bd = [{'nm': grp['nm'], 't': round(ven_fin.get(k, {}).get('bd', {}).get(grp['nm'], 0), 2)} for grp in FINANCEIRAS_GROUPS]
            merged.append({'n': v['n'], 'i': v['i'], 't': v['t'], 'bd': bd})
        top_fin_mes_bd_by_store[sk] = merged

    print(f"\nAtualizando {INDEX_HTML}...")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        content = f.read()

    for sk in STORE_MAP.values():
        if sk not in sales:
            # Na virada de mês (dia 1) sempre zera — evita acumulado do mês anterior
            if dias_decorridos == 1:
                content = update_store(
                    content, sk,
                    total=0, acess_total=0, agend_total=0, agend_top=[],
                    fat_dia=0, top_dia=[], acess_dia=0, acess_dia_top=[],
                    fin_dia=0, top_fin=[], fin_mes=0, top_fin_mes=[],
                    fin_bd=[{'nm': g['nm'], 't': 0} for g in FINANCEIRAS_GROUPS],
                    sellers_top=[], sellers_today=set(),
                )
                print(f"  {sk}: sem vendas — zerado (dia 1 do mês)")
            else:
                print(f"  {sk}: sem dados de vendas, pulando")
            continue
        content = update_store(
            content, sk,
            total          = sales[sk]['total'],
            acess_total    = acess.get(sk, {}).get('total', 0),
            agend_total    = agend.get(sk, {}).get('total', 0),
            agend_top      = agend.get(sk, {}).get('top', []),
            fat_dia        = today_sellers_proc.get(sk, {}).get('total', 0),
            top_dia        = today_sellers_proc.get(sk, {}).get('top', []),
            acess_dia      = acess_dia.get(sk, {}).get('total', 0),
            acess_dia_top  = acess_dia.get(sk, {}).get('top', []),
            fin_dia        = fin.get(sk, {}).get('total', 0),
            top_fin        = fin.get(sk, {}).get('top', []),
            fin_mes        = fin_acum.get(sk, {}).get('total', 0),
            top_fin_mes    = top_fin_mes_bd_by_store.get(sk, []),
            fin_bd         = fin_bd_by_store.get(sk, []),
            sellers_top    = sales[sk]['top'],
            sellers_today  = sellers_today_by_store.get(sk, set()),
        )
        print(f"  {sk}: atualizado")

    # Atualiza diasDecorridos e diasMes no HTML (garante projeção correta)
    import calendar as _cal_main
    dias_mes_atual = _cal_main.monthrange(_now_brt.year, _now_brt.month)[1]
    content = update_dias_decorridos(content, dias_decorridos, dias_mes_atual, start, today)
    print(f"  diasDecorridos → {dias_decorridos}, diasMes → {dias_mes_atual}")

    # Atualiza margem_dia (margem bruta do dia) — zera se não houver vendas ainda
    margem_dia_final = margem_dia if margem_dia is not None else 0.0
    content = update_margem_dia(content, margem_dia_final)
    print(f"  margem_dia atualizado: {margem_dia_final:.2f}%")

    # Atualiza margem_mes da rede
    if margem_rede is not None:
        content = update_margem_rede(content, margem_rede)
        print(f"  margem_mes atualizado: {margem_rede:.2f}%")

    # Atualiza margem_subredes
    if margem_subredes:
        content = update_margem_subredes(content, margem_subredes)

    # Atualiza margem_dia_subredes — zera subredes sem vendas no dia
    for sub in SUBREDE_LOJAS:
        if sub not in margem_dia_subredes:
            margem_dia_subredes[sub] = 0.0
    content = update_margem_dia_subredes(content, margem_dia_subredes)

    # Atualiza o timestamp de build (força browsers a recarregar após deploy)
    from datetime import datetime as _dt
    build_ts = _dt.now().strftime('%Y%m%d%H%M%S')
    content = re.sub(r"'__BUILD_TS__'", f"'{build_ts}'", content)
    content = re.sub(r"'20\d{12}'", f"'{build_ts}'", content)

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\nindex.html salvo com sucesso! (build: {build_ts})")

    # Gravar total do fat_dia para o check_threshold do próximo run
    fat_dia_total = sum(
        today_sellers_proc.get(sk, {}).get('total', 0) for sk in STORE_MAP.values()
    )
    total_out = os.environ.get('UPDATE_TOTAL_OUTPUT', '')
    if total_out:
        with open(total_out, 'w') as f:
            f.write(str(round(fat_dia_total, 2)))
        print(f"Total fat_dia salvo: R$ {fat_dia_total:,.2f}")

    # Atualiza Firestore em tempo real — dispara onSnapshot em todos os browsers abertos
    print("\nSincronizando com Firestore...")
    save_d360_to_firestore(sales, acess, acess_dia, today_sellers_proc, fin, fin_acum, agend)

if __name__ == '__main__':
    main()

