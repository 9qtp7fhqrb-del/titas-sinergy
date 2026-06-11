#!/usr/bin/env python3
"""
D360 Titãs Sinergy — Atualização automática via API ERP CDC
Atualiza por loja: total, acessorios.total, agendFat, agendamentos.total, agendamentos.top
"""
import re, os, sys
from datetime import date

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

ERP_BASE = 'https://apicdc.casadocelular.com.br/api/v1'
INDEX_HTML = os.environ.get('INDEX_HTML', 'index.html')

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
    """Retorna (start, end) da seção do store no HTML."""
    marker = f'\n        {store_key}:'
    start = content.find(marker)
    if start == -1:
        return None, None
    end = len(content)
    for sk in STORE_MAP.values():
        if sk == store_key:
            continue
        pos = content.find(f'\n        {sk}:', start + 1)
        if 0 < pos < end:
            end = pos
    return start, end

def fmt_top(top_list):
    items = [f"{{n:'{e['n']}',i:'{e['i']}',t:{e['t']}}}" for e in top_list]
    return '[' + ', '.join(items) + ']'

def update_store(content, store_key, total, acess_total, agend_total, agend_top, sellers_top=None, sellers_today=None):
    start, end = find_section(content, store_key)
    if start is None:
        print(f"  AVISO: seção '{store_key}' não encontrada no HTML")
        return content

    sec = content[start:end]

    # 1. total (na linha principal da loja)
    sec = re.sub(r'(\btotal:)\d+(?:\.\d+)?(?=\s*,\s*ped:)', f'\\g<1>{total}', sec, count=1)

    # 2. agendFat
    sec = re.sub(r'\bagendFat:\d+(?:\.\d+)?', f'agendFat:{agend_total}', sec, count=1)

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
        # Substituir o ÚLTIMO top:[] da seção (top principal de vendas)
        all_tops_new = list(re.finditer(r'\btop:\[[\s\S]*?\](?=\s*[\}\]])', sec))
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

    # Se gerou token novo, salva para o workflow persistir no cache
    if is_new_token:
        token_out = os.environ.get('ERP_TOKEN_OUTPUT', '')
        if token_out:
            with open(token_out, 'w') as f:
                f.write(token)
            print(f"Token salvo em {token_out}")

    today = date.today().strftime('%Y-%m-%d')
    start = date.today().strftime('%Y-%m-01')
    print(f"Período: {start} → {today}")

    print("Buscando vendas gerais (acumulado)...")
    sales_data = fetch_sales(token, start, today)

    print("Buscando vendas do dia (para atualizar ult/ds)...")
    today_data = fetch_sales(token, today, today)

    print("Buscando Central de Agendamentos (canal 6)...")
    agend_data = fetch_sales(token, start, today, channel_id=6)

    sales = process(sales_data, lambda c: c.get('total_sold', 0))
    acess = process(sales_data, lambda c: (c.get('group_totals') or {}).get('ACESSÓRIOS', 0))
    agend = process(agend_data, lambda c: (c.get('group_totals') or {}).get('SBON', 0))

    # Set de (store_key, nome_lower) que venderam HOJE
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
        print(f"  {sk:<15} total={s:>10,.2f} | acess={a:>8,.2f} | agend={ag:>10,.2f}")

    print(f"\nAtualizando {INDEX_HTML}...")
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        content = f.read()

    for sk in STORE_MAP.values():
        if sk not in sales:
            print(f"  {sk}: sem dados de vendas, pulando")
            continue
        content = update_store(
            content, sk,
            total          = sales[sk]['total'],
            acess_total    = acess.get(sk, {}).get('total', 0),
            agend_total    = agend.get(sk, {}).get('total', 0),
            agend_top      = agend.get(sk, {}).get('top', []),
            sellers_top    = sales[sk]['top'],
            sellers_today  = sellers_today_by_store.get(sk, set()),
        )
        print(f"  {sk}: atualizado")

    # Atualiza o timestamp de build (força browsers a recarregar após deploy)
    from datetime import datetime as _dt
    build_ts = _dt.now().strftime('%Y%m%d%H%M%S')
    content = re.sub(r"'__BUILD_TS__'", f"'{build_ts}'", content)
    content = re.sub(r"'20\d{12}'", f"'{build_ts}'", content)

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\nindex.html salvo com sucesso! (build: {build_ts})")

if __name__ == '__main__':
    main()
