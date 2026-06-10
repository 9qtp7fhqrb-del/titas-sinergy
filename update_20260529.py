#!/usr/bin/env python3
"""Apply 29/05/2026 sales data update to index.html"""

import re

file_path = '/Users/marcelolima/Documents/Claude/Projects/titas sinergy/index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

original_content = content

# ─────────────────────────────────────────────
# 1. Store totals  (total, ped, cancel)
# ─────────────────────────────────────────────
store_totals = {
    'saomateus':    (384493.73, 364, 3),
    'cariacica':    (354713.14, 279, 6),
    'moxuara':      (289770.49, 303, 2),
    'itabuna':      (236094.0,  295, 4),
    'teixeira':     (220184.99, 246, 4),
    'barreiras':    (214050.0,  202, 4),
    'serra':        (163776.94, 196, 2),
    'laranjeiras':  (166725.15, 140, 0),
    'linhares':     (138216.99, 142, 1),
    'montserrat':   (123433.0,  221, 2),
    'praiadacosta': (75536.0,    58, 0),
}

def fmt_num(v):
    """Format number: int if whole, else keep decimals."""
    if v == int(v):
        return str(int(v))
    return str(v)

for store, (total, ped, cancel) in store_totals.items():
    # Pattern: store_key:{ ... total:OLD_VAL, ped:OLD_PED, cancel:OLD_CANCEL
    pattern = rf'({re.escape(store)}:\s*\{{[^}}]*?total:)([\d.]+)(,ped:)(\d+)(,cancel:)(\d+)'
    def make_replacement(total=total, ped=ped, cancel=cancel):
        def repl(m):
            return m.group(1) + fmt_num(total) + m.group(3) + str(ped) + m.group(5) + str(cancel)
        return repl
    new_content = re.sub(pattern, make_replacement(), content, count=1)
    if new_content == content:
        print(f"WARNING: store total not changed for {store}")
    else:
        print(f"OK store total: {store}")
    content = new_content

# ─────────────────────────────────────────────
# 2. Acessorios totals
# ─────────────────────────────────────────────
acess_totals = {
    'saomateus':    16109.94,
    'cariacica':    10465.15,
    'moxuara':      17580.0,
    'itabuna':      11084.0,
    'teixeira':     5259.0,
    'barreiras':    5462.0,
    'serra':        10919.94,
    'laranjeiras':  2789.0,
    'linhares':     5764.99,
    'montserrat':   14945.0,
    'praiadacosta': 2250.0,
}

for store, total in acess_totals.items():
    # Pattern: store_key:{ ... acessorios:{total:OLD_VAL,
    pattern = rf'({re.escape(store)}:\s*\{{.*?acessorios:\{{total:)([\d.]+)(,)'
    def make_replacement(total=total):
        def repl(m):
            return m.group(1) + fmt_num(total) + m.group(3)
        return repl
    new_content = re.sub(pattern, make_replacement(), content, count=1, flags=re.DOTALL)
    if new_content == content:
        print(f"WARNING: acess total not changed for {store}")
    else:
        print(f"OK acess total: {store}")
    content = new_content

# ─────────────────────────────────────────────
# 3. Vendor updates in acessorios.top[]
# ─────────────────────────────────────────────
# Each vendor entry looks like: {n:'Full Name',i:'XX',t:VAL,ds:VAL,ult:'DD/MM'}
# We do targeted replacements by name.

vendor_updates = {
    'saomateus': [
        # name fragment to match (case-insensitive partial), new t, new ds, new ult
        ('Eliza Queiroz',       3421.98, 24, '29/05'),
        ('Stefany Sperotto',    1468,    18, '29/05'),
        ('Leandro Da Cruz',     1030,    16, '29/05'),
    ],
    'cariacica': [
        ('Roberta Felipe',      5135,    22, '29/05'),
        ('Liz Sophia',          3520.15, 23, '29/05'),
        ('Glaupierre',          1580,    21, '29/05'),
    ],
    'moxuara': [
        ('Khayllane',           8090,    22, '29/05'),
        ('Iasmim',              3700,    21, '29/05'),
    ],
    'itabuna': [
        ('Hericles Lisboa',     2835,    21, '29/05'),
        ('Sandy De Araujo',     1325,    10, '29/05'),
        ('Andreza De Jesus',    1085,    14, '29/05'),
    ],
    'teixeira': [
        ('Carine Ferreira',     2110,    20, '29/05'),
        ('Paloma De Jesus',     603,     17, '29/05'),
        ('Beatriz Hellen',      375,     15, '29/05'),
    ],
    'barreiras': [
        ('Isabela Chagas',      625,     20, '29/05'),
        ('Larisse Ribeiro',     960.01,  14, '29/05'),
        ('Táine Oliveira',      530,     15, '29/05'),
        ('Maria Fernanda',      130,     3,  '29/05'),
    ],
    'serra': [
        ('Lucas Loyola',        3524.99, 17, '29/05'),
        ('Karen Scavelo',       2224.99, 20, '29/05'),
        ('Luiz Henrique',       1729.99, 16, '29/05'),
    ],
    'laranjeiras': [
        ('Mayara Kull',         1079,    19, '29/05'),
        ('Nycolly Calazans',    450,     12, '29/05'),
    ],
    'linhares': [
        ('Natalia Rocha',       1705,    19, '29/05'),
        ('Krystian Lincoln',    250,     4,  '29/05'),
    ],
    'montserrat': [
        ('Joaquin Emiliano',    5850,    18, '29/05'),
        ('Vinicius De Almeida', 1580,    19, '29/05'),
    ],
    # praiadacosta: ADD new vendor (handled separately below)
}

for store, vendors in vendor_updates.items():
    for name_frag, t, ds, ult in vendors:
        # Build pattern: {n:'...name_frag...',i:'XX',t:OLD,ds:OLD,ult:'OLD'}
        # name_frag may have different casing in file; use case-insensitive
        pattern = (
            r"(\{n:'" + re.escape(name_frag) + r"[^']*',i:'[^']+',t:)"
            r"([\d.]+)"
            r"(,ds:)"
            r"(\d+)"
            r"(,ult:')"
            r"([^']+)"
            r"(')"
        )
        def make_vend_repl(t=t, ds=ds, ult=ult):
            def repl(m):
                return m.group(1) + fmt_num(t) + m.group(3) + str(ds) + m.group(5) + ult + m.group(7)
            return repl
        new_content = re.sub(pattern, make_vend_repl(), content, count=1, flags=re.IGNORECASE)
        if new_content == content:
            print(f"WARNING: vendor not changed: {store} / {name_frag}")
        else:
            print(f"OK vendor: {store} / {name_frag}")
        content = new_content

# praiadacosta: add new vendor entry {n:'Filipe Mattos Queiroz',i:'FM',t:200,ds:1,ult:'29/05'}
# Find the praiadacosta acessorios top array and append before its closing ]
# The top array ends with: ...ult:'DD/MM'}],dias:
# We insert before the }],dias: inside praiadacosta's acessorios block

new_vendor_entry = "{n:'Filipe Mattos Queiroz',i:'FM',t:200,ds:1,ult:'29/05'}"

# Find praiadacosta block and its acessorios top array closing
# Pattern: last vendor in praiadacosta top array followed by }],dias:
pattern = r"(praiadacosta:\{[^\}]*?acessorios:\{total:[^\}]*?top:\[.*?)\]\},dias:"
def add_vendor(m):
    # append new vendor to top array
    existing = m.group(1)
    return existing + ',' + new_vendor_entry + ']},dias:'

new_content = re.sub(pattern, add_vendor, content, count=1, flags=re.DOTALL)
if new_content == content:
    print("WARNING: praiadacosta new vendor not added")
else:
    print("OK vendor: praiadacosta / Filipe Mattos Queiroz (new entry)")
content = new_content

# ─────────────────────────────────────────────
# 4. Append dias entries
# ─────────────────────────────────────────────
dias_entries = {
    'saomateus':    "{d:'29/05',ac:5,cel:7}",
    'cariacica':    "{d:'29/05',ac:2,cel:11}",
    'moxuara':      "{d:'29/05',ac:5,cel:4}",
    'itabuna':      "{d:'29/05',ac:4,cel:5}",
    'teixeira':     "{d:'29/05',ac:4,cel:4}",
    'barreiras':    "{d:'29/05',ac:4,cel:4}",
    'serra':        "{d:'29/05',ac:4,cel:2}",
    'laranjeiras':  "{d:'29/05',ac:2,cel:7}",
    'linhares':     "{d:'29/05',ac:3,cel:2}",
    'montserrat':   "{d:'29/05',ac:6,cel:4}",
    'praiadacosta': "{d:'29/05',ac:1,cel:0}",
}

for store, entry in dias_entries.items():
    # Find the dias array for this store: dias:[...LAST_ENTRY]}, top:[
    # We need to append entry before the closing ] of dias
    # Pattern: dias:[...{d:'28/05'...}] followed by ]},
    # Use store-specific pattern: find store block then its dias array closing
    pattern = (
        r'(' + re.escape(store) + r':\s*\{.*?dias:\[.*?\{d:\'[^\']+\',[^\}]+\})'
        r'(\]\})'
    )
    def make_dias_repl(entry=entry):
        def repl(m):
            return m.group(1) + ',' + entry + m.group(2)
        return repl
    new_content = re.sub(pattern, make_dias_repl(), content, count=1, flags=re.DOTALL)
    if new_content == content:
        print(f"WARNING: dias not appended for {store}")
    else:
        print(f"OK dias: {store}")
    content = new_content

# ─────────────────────────────────────────────
# 5. Update _HIST_ACESS_MAI26
# ─────────────────────────────────────────────
# periodo
old_periodo = "periodo: '01/05/2026 – 28/05/2026'"
new_periodo = "periodo: '01/05/2026 – 29/05/2026'"
if old_periodo in content:
    content = content.replace(old_periodo, new_periodo, 1)
    print("OK _HIST_ACESS_MAI26 periodo")
else:
    print("WARNING: _HIST_ACESS_MAI26 periodo not found, trying regex")
    pattern = r"(_HIST_ACESS_MAI26\s*=\s*\{[^}]*?periodo:\s*')(01/05/2026\s*[–-]\s*28/05/2026)(')"
    new_content = re.sub(pattern, lambda m: m.group(1) + '01/05/2026 – 29/05/2026' + m.group(3), content, count=1, flags=re.DOTALL)
    if new_content == content:
        print("WARNING: _HIST_ACESS_MAI26 periodo still not changed")
    else:
        print("OK _HIST_ACESS_MAI26 periodo (regex)")
    content = new_content

# totalGeral: find within _HIST_ACESS_MAI26 block
# Find the block: var _HIST_ACESS_MAI26 = { ... totalGeral: OLD, totalUN: OLD,
pattern = r'(var _HIST_ACESS_MAI26\s*=\s*\{.*?totalGeral:\s*)([\d.]+)'
new_content = re.sub(pattern, lambda m: m.group(1) + '102629.02', content, count=1, flags=re.DOTALL)
if new_content == content:
    print("WARNING: _HIST_ACESS_MAI26 totalGeral not changed")
else:
    print("OK _HIST_ACESS_MAI26 totalGeral")
content = new_content

# totalUN
pattern = r'(var _HIST_ACESS_MAI26\s*=\s*\{.*?totalUN:\s*)(\d+)'
new_content = re.sub(pattern, lambda m: m.group(1) + '1394', content, count=1, flags=re.DOTALL)
if new_content == content:
    print("WARNING: _HIST_ACESS_MAI26 totalUN not changed")
else:
    print("OK _HIST_ACESS_MAI26 totalUN")
content = new_content

# ─────────────────────────────────────────────
# Write result
# ─────────────────────────────────────────────
if content == original_content:
    print("\nERROR: No changes were made!")
else:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("\nFile written successfully.")
