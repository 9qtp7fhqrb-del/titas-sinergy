#!/usr/bin/env python3
"""Apply 30/05/2026 sales data update to index.html and bump sw.js."""

import re

INDEX = "/Users/marcelolima/Documents/Claude/Projects/titas sinergy/index.html"
SW    = "/Users/marcelolima/Documents/Claude/Projects/titas sinergy/sw.js"

with open(INDEX, 'r', encoding='utf-8') as f:
    html = f.read()

# ── 1. Store totals ──────────────────────────────────────────────────────────

store_totals = {
    'saomateus':    (384493.73, 364, 3,  400063.73, 378, 3),
    'cariacica':    (354713.14, 279, 6,  367763.14, 295, 6),
    'moxuara':      (289770.49, 303, 2,  298244.49, 317, 2),
    'itabuna':      (236094.0,  295, 4,  241284.0,  302, 4),
    'teixeira':     (220184.99, 246, 4,  233514.99, 259, 4),
    'barreiras':    (214050.0,  202, 4,  227649.0,  215, 4),
    'serra':        (163776.94, 196, 2,  168866.94, 208, 3),
    'laranjeiras':  (166725.15, 140, 0,  171525.15, 144, 0),
    'linhares':     (138216.99, 142, 1,  141196.99, 146, 1),
    'montserrat':   (123433.0,  221, 2,  126272.99, 227, 2),
    'praiadacosta': (75536.0,    58, 0,   75866.0,   60, 0),
}

def fmt_num(v):
    """Format number: drop .0 suffix when value is whole, else keep decimals."""
    if v == int(v):
        return str(int(v))
    # strip trailing zeros after decimal
    s = f"{v}"
    return s

for store, (ot, op, oc, nt, np, nc) in store_totals.items():
    old = f"total:{fmt_num(ot)}, ped:{op}, cancel:{oc}"
    new = f"total:{fmt_num(nt)}, ped:{np}, cancel:{nc}"
    if old not in html:
        # try without spaces
        old = f"total:{fmt_num(ot)},ped:{op},cancel:{oc}"
        new = f"total:{fmt_num(nt)},ped:{np},cancel:{nc}"
    count = html.count(old)
    if count == 0:
        print(f"WARNING: store total pattern not found for {store}: {old!r}")
    else:
        html = html.replace(old, new, 1)
        print(f"OK store total {store}: {old!r} -> {new!r}")

# ── 2. Acessorios totals ──────────────────────────────────────────────────────

# Pattern inside acessorios block: acessorios:{total:OLD,...
acess_totals = {
    'saomateus':    (16109.94, 16829.94),
    'cariacica':    (10465.15, 11145.15),
    'moxuara':      (17580,    18050.0),
    'itabuna':      (11084,    11134.0),
    'teixeira':     (5259,     5439.0),
    'barreiras':    (5462,     6462.0),
    'serra':        (10919.94, 12479.94),
    'laranjeiras':  (2789,     2814.0),
    'linhares':     (5764.99,  5844.99),
    'montserrat':   (14945,    16285.0),
    'praiadacosta': (2250,     2580.0),
}

for store, (old_v, new_v) in acess_totals.items():
    old = f"acessorios:{{total:{fmt_num(old_v)}"
    new = f"acessorios:{{total:{fmt_num(new_v)}"
    if old not in html:
        print(f"WARNING: acessorios total not found for {store}: {old!r}")
    else:
        html = html.replace(old, new, 1)
        print(f"OK acess total {store}")

# ── 3. Vendor updates ────────────────────────────────────────────────────────

# Each vendor entry: {n:'Name',i:'XX',t:OLD,ds:OLD,ult:'OLD'}
# We only update t, ds, ult fields

vendors = [
    # saomateus
    ("Alice Christino Monteiro",                   "AC", 3054.99, 21, "28/05",  3084.99, 22, "30/05"),
    ("Crislany Oliveira Olegario",                 "CO", 210.0,   3,  "27/05",  250,     4,  "30/05"),
    ("Eliza Queiroz De Souza",                     "EQ", 3421.98, 24, "29/05",  3801.98, 25, "30/05"),
    ("Leandro Da Cruz Silva",                      "LC", 1030,    16, "29/05",  1180,    17, "30/05"),
    ("Stefany Sperotto Barcelos",                  "SB", 1468,    18, "29/05",  1588,    19, "30/05"),
    # cariacica
    ("Glaupierre Oliveira Da Silvaa",              "GO", 1580,    21, "29/05",  1760,    22, "30/05"),
    ("Liz Sophia Andrade Pereira",                 "LS", 3520.15, 23, "29/05",  3780.15, 24, "30/05"),
    ("Roberta Felipe Malaquias",                   "RF", 5135,    22, "29/05",  5375,    23, "30/05"),
    # moxuara
    ("Iasmim Vitoria Medeiros Gaio",               "IV", 3700,    21, "29/05",  3740,    22, "30/05"),
    ("Khayllane De Almeida Ferreira",              "KA", 8090,    22, "29/05",  8340,    23, "30/05"),
    ("Luccas Da Silva Medeiros Martins",           "LM", 1370.0,  8,  "27/05",  1460,    9,  "30/05"),
    ("Mirelly Vieira Portugal",                    "MV", 1790.0,  10, "19/05",  1880,    11, "30/05"),
    # itabuna
    ("Keifit Moreira Dos Santos",                  "KM", 1064.0,  17, "26/05",  1089,    18, "30/05"),
    ("Sandy De Araujo Santos Lima",                "SA", 1325,    10, "29/05",  1350,    11, "30/05"),
    # teixeira
    ("Amanda Goulart Andrade",                     "AG", 905.0,   16, "28/05",  945,     17, "30/05"),
    ("Carine Ferreira Franco",                     "CF", 2110,    20, "29/05",  2190,    21, "30/05"),
    ("Carla Santos Luiz",                          "CS", 761.0,   18, "28/05",  821,     19, "30/05"),
    # barreiras
    ("Isabela Chagas",                             "IC", 625,     20, "29/05",  725,     21, "30/05"),
    ("Larisse Ribeiro Dos Santos",                 "LR", 960.01,  14, "29/05",  1220.01, 15, "30/05"),
    ("Victor Roberto De Oliveira Nascimento",      "VR", 960.0,   20, "28/05",  1600,    21, "30/05"),
    # serra
    ("Karen Scavelo Souza",                        "KS", 2224.99, 20, "29/05",  2544.99, 21, "30/05"),
    ("Lucas Loyola Araujo",                        "LL", 3524.99, 17, "29/05",  4434.99, 18, "30/05"),
    ("Luiz Henrique Viana Da Rocha",               "LH", 1729.99, 16, "29/05",  1939.99, 17, "30/05"),
    ("Marcela Da Silva Lopes",                     "MS", 3279.99, 17, "28/05",  3399.99, 18, "30/05"),
    # laranjeiras
    ("Mayara Kull Rodrigues",                      "MK", 1079,    19, "29/05",  1104,    20, "30/05"),
    # linhares
    ("Rayca Mendes Morais",                        "RM", 3569.99, 18, "26/05",  3649.99, 19, "30/05"),
    # montserrat
    ("Joaquin Emiliano Rodrigo",                   "JR", 5850,    18, "29/05",  6940,    19, "30/05"),
    ("Vinicius De Almeida Medeiros Vargas",        "VV", 1580,    19, "29/05",  1830,    20, "30/05"),
    # praiadacosta
    ("Filipe Mattos Queiroz",                      "FM", 200,     1,  "29/05",  430,     2,  "30/05"),
    ("Renato Lembranci Metzke Junior",             "RL", 850.0,   13, "27/05",  950,     14, "30/05"),
]

for name, initials, ot, ods, oult, nt, nds, nult in vendors:
    old = f"{{n:'{name}',i:'{initials}',t:{fmt_num(ot)},ds:{ods},ult:'{oult}'}}"
    new = f"{{n:'{name}',i:'{initials}',t:{fmt_num(nt)},ds:{nds},ult:'{nult}'}}"
    if old not in html:
        print(f"WARNING: vendor pattern not found: {old!r}")
    else:
        html = html.replace(old, new, 1)
        print(f"OK vendor {name}")

# ── 4. Dias entries ──────────────────────────────────────────────────────────

dias_new = {
    'saomateus':    "{d:'30/05',ac:5,cel:9}",
    'cariacica':    "{d:'30/05',ac:8,cel:8}",
    'moxuara':      "{d:'30/05',ac:8,cel:6}",
    'itabuna':      "{d:'30/05',ac:2,cel:5}",
    'teixeira':     "{d:'30/05',ac:3,cel:10}",
    'barreiras':    "{d:'30/05',ac:4,cel:4}",   # barreiras last entry is 29/05 ac:4 cel:4
    'serra':        "{d:'30/05',ac:8,cel:4}",
    'laranjeiras':  "{d:'30/05',ac:1,cel:3}",
    'linhares':     "{d:'30/05',ac:2,cel:2}",
    'montserrat':   "{d:'30/05',ac:4,cel:2}",
    'praiadacosta': "{d:'30/05',ac:2,cel:0}",
}

# Last known 29/05 entries for each store (from grep output above)
last_entries = {
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

for store, last_entry in last_entries.items():
    new_entry = dias_new[store]
    anchor = last_entry
    if anchor not in html:
        print(f"WARNING: dias anchor not found for {store}: {anchor!r}")
    else:
        html = html.replace(anchor, anchor + "," + new_entry, 1)
        print(f"OK dias {store}")

# ── 5. _HIST_ACESS_MAI26 ────────────────────────────────────────────────────

html = html.replace(
    "periodo: '01/05/2026 – 29/05/2026'",
    "periodo: '01/05/2026 – 30/05/2026'"
)
print("OK periodo")

html = html.replace("totalGeral: 102629.02,", "totalGeral: 109064.02,")
print("OK totalGeral")

html = html.replace("totalUN: 1394,", "totalUN: 1462,")
print("OK totalUN")

# ── Write index.html ─────────────────────────────────────────────────────────

with open(INDEX, 'w', encoding='utf-8') as f:
    f.write(html)
print("\nindex.html written.")

# ── 6. Bump sw.js ────────────────────────────────────────────────────────────

with open(SW, 'r', encoding='utf-8') as f:
    sw = f.read()

sw = sw.replace("'titas-sinergy-v38'", "'titas-sinergy-v39'")
with open(SW, 'w', encoding='utf-8') as f:
    f.write(sw)
print("sw.js bumped to v39.")
