#!/usr/bin/env python3
"""
Atualiza a aba FLOW e 360° do titas-sinergy/index.html
com os dados mais recentes dos CSVs de Acompanhamento geral.

Uso:
    python3 atualizar_dados.py

Execute sempre que adicionar um novo arquivo vendas-XX.csv.
"""

import csv, io, os, re
from collections import defaultdict
from datetime import datetime

PASTA_DADOS = "/Users/marcelolima/Documents/Claude/Projects/Acompanhamento geral"
HTML_ALVO   = "/Users/marcelolima/Documents/Claude/Projects/titas sinergy/index.html"

META_REDE      = 3_000_000
META_PEDIDOS   = 2_500
META_TICKET    = 1_500
META_T1        = 1_200_000
META_T2        =   800_000
META_T3        = 1_000_000

SUBREDE_MAP = {
    'MOXUARA':       'Titãs 1', 'CARIACICA':  'Titãs 1',
    'ITABUNA':       'Titãs 1', 'PRAIA DA COSTA': 'Titãs 1',
    'BARREIRAS':     'Titãs 2', 'TEIXEIRA':   'Titãs 2', 'LARANJEIRAS': 'Titãs 2',
    'SAO MATEUS':    'Titãs 3', 'MATEUS':     'Titãs 3',
    'LINHARES':      'Titãs 3', 'SERRA':      'Titãs 3', 'MONTSERRAT':  'Titãs 3',
}

LOJA_LABEL = {
    'CDC CARIACICA':                'Cariacica',
    'CDC ITABUNA':                  'Itabuna',
    'CDC PRAIA DA COSTA':           'Praia da Costa',
    'SHOPPING MOXUARA':             'Moxuara',
    'CDC BARREIRAS':                'Barreiras',
    'CDC TEIXEIRA DE FREITAS NOVO': 'Teixeira de Freitas',
    'CDC LARANJEIRAS':              'Laranjeiras',
    'CDC SAO MATEUS':               'São Mateus',
    'CDC LINHARES':                 'Linhares',
    'CDC SERRA':                    'Serra',
    'CDC MONTSERRAT':               'Montserrat',
}

LOJA_SIGLA = {
    'CDC CARIACICA': 'CC', 'CDC ITABUNA': 'IT', 'CDC PRAIA DA COSTA': 'PC',
    'SHOPPING MOXUARA': 'MX', 'CDC BARREIRAS': 'BR',
    'CDC TEIXEIRA DE FREITAS NOVO': 'TF', 'CDC LARANJEIRAS': 'LJ',
    'CDC SAO MATEUS': 'SM', 'CDC LINHARES': 'LH',
    'CDC SERRA': 'SR', 'CDC MONTSERRAT': 'MT',
}

def get_subrede(loja):
    l = loja.upper()
    for k, v in SUBREDE_MAP.items():
        if k in l:
            return v
    return '?'

def fmt_brl(v):
    if v >= 1_000_000:
        return f'R$ {v/1_000_000:.2f}M'.replace('.', ',')
    if v >= 1_000:
        return f'R$ {v/1_000:.1f}K'.replace('.', ',')
    return f'R$ {v:,.0f}'.replace(',', '.')

def fmt_num(v):
    return f'{v:,}'.replace(',', '.')

def initials(name):
    parts = name.strip().split()
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else name[:2].upper()

# ── 1. Carregar e deduplicar todos os CSVs ─────────────────────────────────
print("Lendo CSVs...")
all_rows = {}
for fname in sorted(os.listdir(PASTA_DADOS)):
    if not fname.endswith('.csv'):
        continue
    try:
        with open(os.path.join(PASTA_DADOS, fname), encoding='utf-8') as f:
            content = f.read()
        reader = csv.DictReader(io.StringIO(content), delimiter=';')
        for r in reader:
            rid = r.get('Id', '').strip()
            if rid:
                all_rows[rid] = r
    except Exception as e:
        print(f"  Aviso: {fname} → {e}")

print(f"  {len(all_rows)} registros únicos carregados.")

# ── 2. Detectar mês corrente e filtrar ─────────────────────────────────────
now = datetime.now()
mes_str = f'{now.month:02d}/{str(now.year)[2:]}'   # ex: "04/26"
mes_label = now.strftime('%b/%y').capitalize()       # ex: "Abr/26"

rows_mes = [r for r in all_rows.values() if mes_str in r.get('    Data    ', '')]
canceladas_list = [r for r in rows_mes if r.get('Status') in ('CANCELADA', 'CANCELADO', 'RECUSADA', 'RECUSADO')]
valid = [r for r in rows_mes if r.get('Status') not in ('CANCELADA', 'CANCELADO', 'RECUSADA', 'RECUSADO')
         and r.get('Valor Total')]

print(f"  Mês {mes_label}: {len(valid)} pedidos válidos, {len(canceladas_list)} cancelamentos.")

if not valid:
    print("Nenhum dado encontrado para o mês corrente. Abortando.")
    exit(1)

total      = sum(float(r['Valor Total']) for r in valid)
pedidos    = len(valid)
canceladas = len(canceladas_list)
ticket     = total / pedidos if pedidos else 0

pct_fat    = round(total / META_REDE * 100)
pct_ped    = round(pedidos / META_PEDIDOS * 100)
pct_ticket = round(ticket / META_TICKET * 100)
pct_cancel = round(canceladas / (pedidos + canceladas) * 100, 1) if (pedidos + canceladas) else 0

# ── 3. Top vendedores ───────────────────────────────────────────────────────
vend_t = defaultdict(float)
vend_p = defaultdict(int)
vend_loja = {}
for r in valid:
    v = r['Vendedor'].strip().title()
    vend_t[v] += float(r['Valor Total'])
    vend_p[v] += 1
    vend_loja[v] = LOJA_LABEL.get(r['Loja'].strip(), r['Loja'].strip().title())

top_vend = sorted(vend_t.items(), key=lambda x: -x[1])[:5]

# ── 4. Top lojas ───────────────────────────────────────────────────────────
loja_t = defaultdict(float)
loja_p = defaultdict(int)
for r in valid:
    loja_t[r['Loja'].strip()] += float(r['Valor Total'])
    loja_p[r['Loja'].strip()] += 1

top_lojas = sorted(loja_t.items(), key=lambda x: -x[1])[:5]
max_loja  = top_lojas[0][1] if top_lojas else 1

# ── 5. Sub-redes ───────────────────────────────────────────────────────────
sub_t = defaultdict(float)
for r in valid:
    sub_t[get_subrede(r['Loja'])] += float(r['Valor Total'])

t1 = sub_t.get('Titãs 1', 0)
t2 = sub_t.get('Titãs 2', 0)
t3 = sub_t.get('Titãs 3', 0)

# ── 6. Gerar HTML dos blocos ───────────────────────────────────────────────

def kpi_cards_flow():
    return f'''            <!-- KPI Grid — dados: {mes_label}, dias 05–{now.day:02d} -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">

                <!-- KPI 1 -->
                <div class="glass rounded-2xl p-4 card-lift cursor-pointer">
                    <div class="flex items-center justify-between mb-3">
                        <i class="fas fa-dollar-sign" style="color:#D4AF37;"></i>
                        <span class="text-[10px] text-green-400 font-bold bg-green-900/30 px-2 py-0.5 rounded-full">{mes_label}</span>
                    </div>
                    <p class="text-2xl font-bold text-white">{fmt_brl(total)}</p>
                    <p class="text-[10px] text-gray-400 mt-0.5">Faturamento Mês</p>
                    <div class="mt-3 h-1.5 bg-gray-800 rounded-full">
                        <div class="prog-bar h-full rounded-full" style="width:{min(pct_fat,100)}%"></div>
                    </div>
                    <p class="text-[10px] text-gray-500 mt-1">{pct_fat}% da meta ({fmt_brl(META_REDE)})</p>
                </div>

                <!-- KPI 2 -->
                <div class="glass rounded-2xl p-4 card-lift cursor-pointer">
                    <div class="flex items-center justify-between mb-3">
                        <i class="fas fa-receipt" style="color:#D4AF37;"></i>
                        <span class="text-[10px] text-green-400 font-bold bg-green-900/30 px-2 py-0.5 rounded-full">{mes_label}</span>
                    </div>
                    <p class="text-2xl font-bold text-white">{fmt_num(pedidos)}</p>
                    <p class="text-[10px] text-gray-400 mt-0.5">Pedidos do Mês</p>
                    <div class="mt-3 h-1.5 bg-gray-800 rounded-full">
                        <div class="prog-bar h-full rounded-full" style="width:{min(pct_ped,100)}%"></div>
                    </div>
                    <p class="text-[10px] text-gray-500 mt-1">{pct_ped}% da meta ({fmt_num(META_PEDIDOS)})</p>
                </div>

                <!-- KPI 3 -->
                <div class="glass rounded-2xl p-4 card-lift cursor-pointer">
                    <div class="flex items-center justify-between mb-3">
                        <i class="fas fa-triangle-exclamation" style="color:#D4AF37;"></i>
                        <span class="text-[10px] text-yellow-400 font-bold bg-yellow-900/30 px-2 py-0.5 rounded-full">{pct_cancel}%</span>
                    </div>
                    <p class="text-2xl font-bold text-white">{canceladas}</p>
                    <p class="text-[10px] text-gray-400 mt-0.5">Cancelamentos</p>
                    <div class="mt-3 h-1.5 bg-gray-800 rounded-full">
                        <div class="h-full rounded-full bg-yellow-700" style="width:{min(int(pct_cancel*10),100)}%"></div>
                    </div>
                    <p class="text-[10px] text-gray-500 mt-1">meta: abaixo de 5%</p>
                </div>

                <!-- KPI 4 -->
                <div class="glass rounded-2xl p-4 card-lift cursor-pointer">
                    <div class="flex items-center justify-between mb-3">
                        <i class="fas fa-fire" style="color:#D4AF37;"></i>
                        <span class="text-[10px] text-green-400 font-bold bg-green-900/30 px-2 py-0.5 rounded-full">{mes_label}</span>
                    </div>
                    <p class="text-2xl font-bold text-white">R$ {int(ticket):,}".replace(",",".")}</p>
                    <p class="text-[10px] text-gray-400 mt-0.5">Ticket Médio</p>
                    <div class="mt-3 h-1.5 bg-gray-800 rounded-full">
                        <div class="prog-bar h-full rounded-full" style="width:{min(pct_ticket,100)}%"></div>
                    </div>
                    <p class="text-[10px] text-gray-500 mt-1">meta: {fmt_brl(META_TICKET)}</p>
                </div>

            </div>'''

def vendedor_item(pos, nome, loja, valor, pedidos_v, primeiro=False):
    ini = initials(nome)
    val_fmt = f'R$ {int(valor):,}'.replace(',', '.')
    if primeiro:
        return f'''                        <div class="flex items-center gap-2.5">
                            <span class="text-base font-black w-6 text-center" style="color:#D4AF37;">1°</span>
                            <div class="w-8 h-8 rounded-full bg-yellow-900/30 flex items-center justify-center text-[10px] font-bold text-yellow-500 flex-shrink-0">{ini}</div>
                            <div class="flex-1 min-w-0">
                                <p class="text-xs text-white font-semibold truncate">{nome}</p>
                                <p class="text-[10px] text-gray-500">{loja} · {val_fmt}</p>
                            </div>
                            <i class="fas fa-crown text-xs flex-shrink-0" style="color:#D4AF37;"></i>
                        </div>'''
    colors = {2: 'text-gray-400', 3: 'text-orange-700', 4: 'text-gray-600', 5: 'text-gray-600'}
    bg = {2: 'bg-gray-800 text-gray-400', 3: 'bg-orange-900/20 text-orange-600',
          4: 'bg-gray-800 text-gray-500', 5: 'bg-gray-800 text-gray-500'}
    txt = {2: 'text-white', 3: 'text-white', 4: 'text-gray-400', 5: 'text-gray-400'}
    sep = '                        <div class="h-px bg-gray-800 my-1"></div>\n' if pos == 4 else ''
    return f'''{sep}                        <div class="flex items-center gap-2.5">
                            <span class="text-{'base' if pos<=3 else 'xs'} font-{'black' if pos<=3 else 'bold'} w-6 text-center {colors[pos]}">{pos}°</span>
                            <div class="w-8 h-8 rounded-full {bg[pos]} flex items-center justify-center text-[10px] font-bold flex-shrink-0">{ini}</div>
                            <div class="flex-1 min-w-0">
                                <p class="text-xs {txt[pos]} {'font-semibold' if pos<=3 else ''} truncate">{nome}</p>
                                <p class="text-[10px] text-gray-{'500' if pos<=3 else '600'}">{loja} · {val_fmt}</p>
                            </div>
                        </div>'''

def top_vend_html():
    items = []
    for i, (nome, val) in enumerate(top_vend, 1):
        loja = vend_loja.get(nome, '')
        items.append(vendedor_item(i, nome, loja, val, vend_p[nome], primeiro=(i==1)))
    return '\n'.join(items)

# ── 7. Substituições no HTML ───────────────────────────────────────────────

with open(HTML_ALVO, encoding='utf-8') as f:
    html = f.read()

def replace_block(html, start_marker, end_marker, new_content):
    pattern = re.escape(start_marker) + r'.*?' + re.escape(end_marker)
    replacement = start_marker + new_content + end_marker
    result, n = re.subn(pattern, replacement, html, flags=re.DOTALL)
    if n == 0:
        print(f"  ⚠️  Marcador não encontrado: {start_marker[:60]}")
    return result

# — KPI cards Flow —
S1 = '<!-- KPI Grid'
E1 = '</div>\n\n            <!-- Rotinas'
html = replace_block(html, S1, E1,
    kpi_cards_flow().split(S1, 1)[1].rsplit(E1.strip(), 1)[0])

# — Top Vendedores Flow —
S2 = '<!-- Top Vendedores — Abr'
E2 = '</div>\n                </div>'
# build replacement vendedor list
vend_block = '\n' + top_vend_html() + '\n                    '
old_pattern = r'<!-- Top Vendedores.*?(<div class="space-y-3">)(.*?)(</div>\s*</div>\s*</div>)'
m = re.search(old_pattern, html, re.DOTALL)
if m:
    html = html[:m.start(2)] + vend_block + html[m.end(2):]

# — Comunicados —
now_str = now.strftime('%d/%m/%y')
top1_nome = top_vend[0][0] if top_vend else '—'
top1_loja = vend_loja.get(top1_nome, '—')
top1_val  = f'R$ {int(top_vend[0][1]):,}'.replace(',', '.') if top_vend else '—'
lider_sub = max(sub_t, key=sub_t.get) if sub_t else '—'
lider_pct = round(sub_t[lider_sub] / total * 100, 1) if total else 0
lider_val = fmt_brl(sub_t[lider_sub])

com_new = f'''            <!-- Comunicados — baseado nos dados de {mes_label} -->
            <div class="glass rounded-2xl p-5">
                <h3 class="text-xs font-bold text-white tracking-widest uppercase mb-4">
                    <i class="fas fa-bell mr-2" style="color:#D4AF37;"></i>Comunicados Recentes
                    <span class="text-gray-600 normal-case font-normal text-[10px] ml-2">Fonte: CSVs · {now_str}</span>
                </h3>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div class="rounded-xl p-3.5 border border-yellow-800/30 bg-yellow-900/10">
                        <p class="text-[10px] text-yellow-400 font-bold tracking-widest mb-1.5">
                            <i class="fas fa-triangle-exclamation mr-1"></i>ATENÇÃO
                        </p>
                        <p class="text-xs text-white font-semibold">Meta do mês em {pct_fat}%</p>
                        <p class="text-[10px] text-gray-400 mt-1">{fmt_brl(total)} de {fmt_brl(META_REDE)} — foco nos dias restantes</p>
                    </div>
                    <div class="rounded-xl p-3.5 border border-green-800/30 bg-green-900/10">
                        <p class="text-[10px] text-green-400 font-bold tracking-widest mb-1.5">
                            <i class="fas fa-star mr-1"></i>DESTAQUE
                        </p>
                        <p class="text-xs text-white font-semibold">{top1_nome.split()[0]} lidera {mes_label}</p>
                        <p class="text-[10px] text-gray-400 mt-1">{top1_val} em {vend_p.get(top1_nome, 0)} pedidos · {top1_loja}</p>
                    </div>
                    <div class="rounded-xl p-3.5 border border-blue-800/30 bg-blue-900/10">
                        <p class="text-[10px] text-blue-400 font-bold tracking-widest mb-1.5">
                            <i class="fas fa-circle-info mr-1"></i>REDE
                        </p>
                        <p class="text-xs text-white font-semibold">{lider_sub} lidera a rede</p>
                        <p class="text-[10px] text-gray-400 mt-1">{lider_pct}% do faturamento · {lider_val} acumulados</p>
                    </div>
                </div>
            </div>'''

html = re.sub(
    r'<!-- Comunicados — baseado.*?</div>\s*</div>',
    com_new + '\n',
    html, flags=re.DOTALL, count=1
)

with open(HTML_ALVO, 'w', encoding='utf-8') as f:
    f.write(html)

print()
print("✅ index.html atualizado com sucesso!")
print(f"   Período  : {mes_label}")
print(f"   Faturamento: {fmt_brl(total)} ({pct_fat}% da meta)")
print(f"   Pedidos  : {fmt_num(pedidos)} | Ticket: R$ {int(ticket):,}".replace(',','.'))
print(f"   Cancelamentos: {canceladas} ({pct_cancel}%)")
print(f"   Top vendedor: {top_vend[0][0]} — {fmt_brl(top_vend[0][1])}")
print(f"   Subrede líder: {lider_sub} ({lider_pct}%)")
