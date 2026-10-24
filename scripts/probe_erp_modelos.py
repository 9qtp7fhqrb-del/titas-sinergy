#!/usr/bin/env python3
"""
Diagnóstico ERP — o que o gerencial retorna por forma de pagamento?
Usa token já salvo no Firestore (sem precisar de login/senha).
"""
import json, sys, os
from datetime import date, timedelta

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

ERP_BASE      = 'https://apicdc.casadocelular.com.br/api/v1'
FIREBASE_KEY  = 'AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8'
FIREBASE_PROJ = 'titas-sinergy'

FINANCEIRAS = [
    {'nm': 'PayJoy',    'ids': [8]},
    {'nm': 'OdresCred', 'ids': [9]},
]

# ── Busca token do Firestore ──────────────────────────────────────────────────

def get_token_from_firestore():
    url = (f'https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJ}'
           f'/databases/(default)/documents/ts_d360_config/erp_session?key={FIREBASE_KEY}')
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    fields = r.json().get('fields', {})
    token = fields.get('token', {}).get('stringValue', '')
    if not token:
        raise ValueError("Token não encontrado no Firestore. Rode o update_d360.py primeiro.")
    return token

# ── Chama gerencial com filtro ────────────────────────────────────────────────

def fetch_gerencial(token, start, end, payment_method_ids=None):
    qs_parts = [f'start_date={start}', f'end_date={end}']
    if payment_method_ids:
        qs_parts += [f'payment_method_ids[]={i}' for i in payment_method_ids]
    url = f'{ERP_BASE}/reports/gerencial?' + '&'.join(qs_parts)
    r = requests.get(url,
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
        timeout=60)
    r.raise_for_status()
    return r.json()

# ── Imprime estrutura de chaves recursivamente ────────────────────────────────

def print_keys(obj, prefix='', depth=0, max_depth=4, max_list=3):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                print(f"{'  '*depth}{prefix}{k}: {{dict, {len(v)} chaves}}")
                print_keys(v, prefix='', depth=depth+1, max_depth=max_depth)
            elif isinstance(v, list):
                print(f"{'  '*depth}{prefix}{k}: [lista, {len(v)} itens]")
                for i, item in enumerate(v[:max_list]):
                    print(f"{'  '*(depth+1)}[{i}]:", end=' ')
                    if isinstance(item, dict):
                        print(f"{{dict: {list(item.keys())[:10]}}}")
                        print_keys(item, depth=depth+2, max_depth=min(max_depth, depth+3))
                    else:
                        print(repr(item)[:120])
                if len(v) > max_list:
                    print(f"{'  '*(depth+1)}... +{len(v)-max_list} itens")
            else:
                val_repr = repr(v)[:80]
                print(f"{'  '*depth}{prefix}{k}: {val_repr}")
    elif isinstance(obj, list):
        print(f"{'  '*depth}[lista raiz, {len(obj)} itens]")
        for i, item in enumerate(obj[:max_list]):
            print_keys(item, prefix=f'[{i}] ', depth=depth+1, max_depth=max_depth)

# ── Busca campos de produto/modelo especificamente ───────────────────────────

def find_product_fields(obj, path='', depth=0, results=None):
    """Procura qualquer campo que sugira modelo/produto/brand/sku."""
    if results is None:
        results = []
    if depth > 6:
        return results
    keywords = ['product', 'model', 'brand', 'sku', 'item', 'celular', 'aparelho',
                'ranking', 'top_', 'more_sold', 'best_sell', 'nome', 'descri']
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_path = f"{path}.{k}" if path else k
            if any(kw in k.lower() for kw in keywords):
                results.append((full_path, type(v).__name__, repr(v)[:200]))
            find_product_fields(v, full_path, depth+1, results)
    elif isinstance(obj, list) and obj:
        find_product_fields(obj[0], f"{path}[0]", depth+1, results)
    return results

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = date.today().strftime('%Y-%m-%d')
    start = date.today().replace(day=1).strftime('%Y-%m-%d')

    print("Buscando token do Firestore...")
    try:
        token = get_token_from_firestore()
        print(f"Token obtido: {token[:20]}...")
    except Exception as e:
        print(f"ERRO ao obter token: {e}")
        sys.exit(1)

    for fin in FINANCEIRAS:
        print(f"\n{'='*60}")
        print(f"FINANCEIRA: {fin['nm']} (ids={fin['ids']}) | {start} → {today}")
        print('='*60)
        try:
            data = fetch_gerencial(token, start, today, payment_method_ids=fin['ids'])

            # Salva resposta completa para inspeção manual
            fname = f"/tmp/erp_{fin['nm'].lower()}.json"
            with open(fname, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"→ Resposta completa salva em {fname}")

            print("\n── Estrutura de chaves ──")
            print_keys(data, max_depth=3, max_list=2)

            print("\n── Campos relacionados a produto/modelo ──")
            found = find_product_fields(data)
            if found:
                for path, typ, val in found:
                    print(f"  {path} ({typ}): {val[:150]}")
            else:
                print("  Nenhum campo de produto/modelo encontrado.")

        except Exception as e:
            print(f"ERRO: {e}")

    # Também testa sem filtro (todas as formas)
    print(f"\n{'='*60}")
    print(f"SEM FILTRO (todas as formas de pagamento) | {start} → {today}")
    print('='*60)
    try:
        data = fetch_gerencial(token, start, today)
        fname = "/tmp/erp_geral.json"
        with open(fname, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"→ Resposta completa salva em {fname}")
        print("\n── Campos relacionados a produto/modelo ──")
        found = find_product_fields(data)
        if found:
            for path, typ, val in found:
                print(f"  {path} ({typ}): {val[:150]}")
        else:
            print("  Nenhum campo de produto/modelo encontrado.")
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == '__main__':
    main()
