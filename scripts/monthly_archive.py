"""
Arquivamento mensal automático — roda via GitHub Actions no 1º dia de cada mês às 02:50 UTC
(= 23:50 BRT no último dia do mês anterior).

O que faz:
  1. Extrai totais finais do D360 do index.html
  2. Salva o mês anterior em ts_d360_historico no Firestore
  3. Atualiza historico_360.json localmente
  4. Faz backup de todas as coleções Firestore acessíveis em backups/YYYY_MM/
"""

import json, re, os, sys, urllib.request, urllib.error
from datetime import date, datetime
from calendar import monthrange

# ── Configuração ─────────────────────────────────────────────────────────────
FSKEY    = 'AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8'
PROJ     = 'titas-sinergy'
HTML     = os.environ.get('INDEX_HTML', 'index.html')
HIST     = 'historico_360.json'
MESES_PT = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

# Mês a arquivar = mês anterior ao dia de hoje (rodando no dia 1 do mês novo)
hoje     = date.today()
prev     = date(hoje.year, hoje.month, 1)  # dia 1 do mês atual
if prev.month == 1:
    prev_y, prev_m = prev.year - 1, 12
else:
    prev_y, prev_m = prev.year, prev.month - 1

chave   = f'{prev_y}_{str(prev_m).zfill(2)}'           # ex: 2026_08
periodo = MESES_PT[prev_m - 1] + ' ' + str(prev_y)     # ex: Ago 2026
dias_mes = monthrange(prev_y, prev_m)[1]

print(f'=== Arquivamento mensal: {periodo} ({chave}) ===\n')


# ── Helpers Firestore REST ─────────────────────────────────────────────────
def fs_get(path, page_size=200):
    url = (f'https://firestore.googleapis.com/v1/projects/{PROJ}'
           f'/databases/(default)/documents/{path}?key={FSKEY}&pageSize={page_size}')
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'_erro': f'HTTP {e.code}'}
    except Exception as e:
        return {'_erro': str(e)}

def fs_patch(path, payload):
    url = (f'https://firestore.googleapis.com/v1/projects/{PROJ}'
           f'/databases/(default)/documents/{path}?key={FSKEY}')
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, method='PATCH',
                                   headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def to_fs(v):
    if isinstance(v, str):   return {'stringValue': v}
    if isinstance(v, bool):  return {'booleanValue': v}
    if isinstance(v, int):   return {'integerValue': str(v)}
    if isinstance(v, float): return {'doubleValue': v}
    if isinstance(v, dict):  return {'mapValue': {'fields': {k: to_fs(vv) for k, vv in v.items()}}}
    if isinstance(v, list):  return {'arrayValue': {'values': [to_fs(i) for i in v]}}
    return {'nullValue': None}

def from_fs(v):
    if not isinstance(v, dict): return v
    for t in ['stringValue','integerValue','doubleValue','booleanValue','nullValue']:
        if t in v: return v[t]
    if 'mapValue'   in v: return {k: from_fs(vv) for k, vv in v['mapValue'].get('fields',{}).items()}
    if 'arrayValue' in v: return [from_fs(i) for i in v['arrayValue'].get('values',[])]
    return v


# ── 1. Extrai totais do index.html ────────────────────────────────────────
print('1. Lendo totais do index.html...')

LOJA_INFO = {
    'cariacica':   ('Cariacica',           'CC', 't1'),
    'itabuna':     ('Itabuna',             'IT', 't1'),
    'moxuara':     ('Moxuara',             'MX', 't1'),
    'barreiras':   ('Barreiras',           'BR', 't2'),
    'teixeira':    ('Teixeira de Freitas', 'TF', 't2'),
    'laranjeiras': ('Laranjeiras',         'LJ', 't2'),
    'praiadacosta':('Praia da Costa',      'PC', 't2'),
    'saomateus':   ('São Mateus',          'SM', 't3'),
    'serra':       ('Serra',               'SR', 't3'),
    'montserrat':  ('Montserrat',          'MT', 't3'),
    'linhares':    ('Linhares',            'LH', 't3'),
}

with open(HTML, encoding='utf-8') as f:
    html = f.read()

lojas_snap = {}
meta_rede  = 0

# Bloco D360.lojas no HTML (entre a primeira ocorrência de "lojas:" dentro do objeto D360)
bloco_match = re.search(r'D360\s*=\s*\{.*?lojas\s*:\s*\{(.*?)\},\s*subredes', html, re.DOTALL)
bloco = bloco_match.group(1) if bloco_match else html

for loja_key, (label, sigla, sub) in LOJA_INFO.items():
    m_total = re.search(rf'{loja_key}\s*:\s*\{{[^}}]*?total\s*:\s*([\d.]+)', bloco)
    m_meta  = re.search(rf'{loja_key}\s*:\s*\{{[^}}]*?meta\s*:\s*([\d.]+)',  bloco)
    m_agend = re.search(rf'{loja_key}\s*:\s*\{{[^}}]*?agend\s*:\s*([\d.]+)', bloco)

    total = float(m_total.group(1)) if m_total else 0.0
    meta  = float(m_meta.group(1))  if m_meta  else 0.0
    agend = float(m_agend.group(1)) if m_agend else 0.0

    lojas_snap[loja_key] = {
        'label': label, 'sigla': sigla, 'sub': sub,
        'meta': meta, 'total': total,
        'ped': 0, 'cancel': 0, 'agend': agend, 'agendCount': 0, 'top': []
    }
    meta_rede += meta
    print(f'   {loja_key:<14} total={total:>12,.2f}  meta={meta:>10,.0f}')

total_rede = sum(v['total'] for v in lojas_snap.values())
print(f'\n   TOTAL REDE: R$ {total_rede:,.2f}  |  META: R$ {meta_rede:,.0f}')

# Se totais vieram zerados, verifica Firestore — se já tiver dados reais, não sobrescreve
usar_firestore_direto = False
if total_rede == 0:
    print('\n   ⚠️  Totais zerados no HTML — verificando Firestore...')
    fs_chk = fs_get(f'ts_d360_historico/{chave}')
    if '_erro' not in fs_chk and fs_chk.get('fields'):
        fs_lojas = fs_chk['fields'].get('lojas', {}).get('mapValue', {}).get('fields', {})
        def _fval(f, key):
            v = f.get(key, {})
            return float(v.get('doubleValue', v.get('integerValue', 0)) or 0)
        fs_total = sum(_fval(v.get('mapValue',{}).get('fields',{}), 'total') for v in fs_lojas.values())
        if fs_total > 0:
            print(f'   Firestore já tem dados reais (R$ {fs_total:,.2f}) — NÃO sobrescreve.')
            usar_firestore_direto = True
            for loja_key in lojas_snap:
                if loja_key in fs_lojas:
                    f = fs_lojas[loja_key].get('mapValue', {}).get('fields', {})
                    lojas_snap[loja_key]['total'] = _fval(f, 'total')
                    lojas_snap[loja_key]['meta']  = _fval(f, 'meta')
            total_rede = sum(v['total'] for v in lojas_snap.values())
            meta_rede  = sum(v['meta']  for v in lojas_snap.values())
            print(f'   TOTAL REDE: R$ {total_rede:,.2f}  |  META: R$ {meta_rede:,.0f}')
        else:
            print('   ❌ Firestore também sem dados — abortando.')
            sys.exit(1)
    else:
        print('   ❌ Firestore sem documento — abortando.')
        sys.exit(1)


# ── 2. Verifica se já existe no Firestore ─────────────────────────────────
print(f'\n2. Verificando Firestore ts_d360_historico/{chave}...')
existing = fs_get(f'ts_d360_historico/{chave}')
if '_erro' not in existing and existing.get('fields'):
    print(f'   Já existe — {"mantendo dados reais" if usar_firestore_direto else "atualizando com dados finais"}.')
else:
    print(f'   Não encontrado — criando entrada.')


# ── 3. Salva no Firestore (só se os dados vieram do HTML — não sobrescreve dados reais já existentes) ──
print(f'\n3. {"Pulando gravação no Firestore (dados reais já existem)." if usar_firestore_direto else f"Salvando {chave} no Firestore..."}')
if usar_firestore_direto:
    pass
else:
  payload = {
      'fields': {
          'periodo':        to_fs(periodo),
          'diasDecorridos': to_fs(dias_mes),
          'diasMes':        to_fs(dias_mes),
          'meta_rede':      to_fs(int(meta_rede)),
          'savedAt':        to_fs(int(datetime.utcnow().timestamp() * 1000)),
          'lojas': {'mapValue': {'fields': {
              k: {'mapValue': {'fields': {
                  'label':  to_fs(v['label']),
                  'sigla':  to_fs(v['sigla']),
                  'sub':    to_fs(v['sub']),
                  'meta':   to_fs(float(v['meta'])),
                  'total':  to_fs(float(v['total'])),
                  'ped':    to_fs(0),
                  'cancel': to_fs(0),
                  'agend':  to_fs(float(v['agend'])),
              }}}
              for k, v in lojas_snap.items()
          }}}
      }
  }
  try:
      fs_patch(f'ts_d360_historico/{chave}', payload)
      print(f'   ✅ ts_d360_historico/{chave} salvo com sucesso')
  except Exception as e:
      print(f'   ❌ Erro ao salvar no Firestore: {e}')
      sys.exit(1)


# ── 4. Atualiza historico_360.json ────────────────────────────────────────
print(f'\n4. Atualizando {HIST}...')
with open(HIST, encoding='utf-8') as f:
    hist_data = json.load(f)

hist_data[chave] = {
    'diasDecorridos': dias_mes,
    'diasMes':        dias_mes,
    'meta_rede':      int(meta_rede),
    'periodo':        periodo,
    'savedAt':        int(datetime.utcnow().timestamp() * 1000),
    'lojas':          lojas_snap,
    'subredes': {
        't1': {'gestor': 'Talysson', 'lojas': ['cariacica','itabuna','moxuara'],
               'meta': int(sum(lojas_snap[k]['meta'] for k in ['cariacica','itabuna','moxuara'])),
               'nome': 'Titãs 1'},
        't2': {'gestor': 'Adriel', 'lojas': ['praiadacosta','barreiras','teixeira','laranjeiras'],
               'meta': int(sum(lojas_snap[k]['meta'] for k in ['praiadacosta','barreiras','teixeira','laranjeiras'])),
               'nome': 'Titãs 2'},
        't3': {'gestor': 'Arthur', 'lojas': ['saomateus','serra','montserrat','linhares'],
               'meta': int(sum(lojas_snap[k]['meta'] for k in ['saomateus','serra','montserrat','linhares'])),
               'nome': 'Titãs 3'},
    }
}

# Ordena por chave
hist_sorted = dict(sorted(hist_data.items()))
with open(HIST, 'w', encoding='utf-8') as f:
    json.dump(hist_sorted, f, ensure_ascii=False, indent=2)
print(f'   ✅ {HIST} atualizado ({len(hist_sorted)} meses)')


# ── 5. Backup completo das coleções Firestore ─────────────────────────────
backup_dir = f'backups/{chave}'
os.makedirs(backup_dir, exist_ok=True)
print(f'\n5. Backup Firestore → {backup_dir}/')

COLECOES = [
    ('ts_d360_historico', 'Histórico mensal'),
    ('ts_diagnostico',    'Diagnóstico'),
    ('ts_d360',           'D360 atual'),
]

for col_id, label in COLECOES:
    resp = fs_get(col_id)
    if '_erro' in resp:
        print(f'   ⚠️  {label}: {resp["_erro"]}')
        continue
    docs = resp.get('documents', [])
    out  = {}
    for d in docs:
        doc_id = d['name'].split('/')[-1]
        out[doc_id] = {k: from_fs(v) for k, v in d.get('fields', {}).items()}
    path = f'{backup_dir}/{col_id}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'   ✅ {label}: {len(docs)} docs → {path}')

# Copia historico_360.json para o backup
import shutil
shutil.copy2(HIST, f'{backup_dir}/historico_360.json')
print(f'   ✅ historico_360.json copiado para {backup_dir}/')

print(f'\n✅ Arquivamento de {periodo} concluído.')
