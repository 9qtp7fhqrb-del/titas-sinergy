#!/usr/bin/env python3
"""Fix remaining issues after update_30_05.py run."""

INDEX = "/Users/marcelolima/Documents/Claude/Projects/titas sinergy/index.html"

with open(INDEX, 'r', encoding='utf-8') as f:
    html = f.read()

# ── Fix store totals that use .0 suffix ──────────────────────────────────────

fixes = [
    # itabuna
    ("total:236094.0, ped:295, cancel:4", "total:241284.0, ped:302, cancel:4"),
    # barreiras
    ("total:214050.0, ped:202, cancel:4", "total:227649.0, ped:215, cancel:4"),
    # montserrat
    ("total:123433.0, ped:221, cancel:2", "total:126272.99, ped:227, cancel:2"),
    # praiadacosta
    ("total:75536.0, ped:58, cancel:0",  "total:75866.0, ped:60, cancel:0"),

    # ── Fix vendors with .0 suffix ──────────────────────────────────────────
    # Crislany
    ("{n:'Crislany Oliveira Olegario',i:'CO',t:210.0,ds:3,ult:'27/05'}",
     "{n:'Crislany Oliveira Olegario',i:'CO',t:250,ds:4,ult:'30/05'}"),
    # Luccas (moxuara - note: praiadacosta entry is different so only replace moxuara)
    ("{n:'Luccas Da Silva Medeiros Martins',i:'LM',t:1370.0,ds:8,ult:'27/05'}",
     "{n:'Luccas Da Silva Medeiros Martins',i:'LM',t:1460,ds:9,ult:'30/05'}"),
    # Mirelly
    ("{n:'Mirelly Vieira Portugal',i:'MV',t:1790.0,ds:10,ult:'19/05'}",
     "{n:'Mirelly Vieira Portugal',i:'MV',t:1880,ds:11,ult:'30/05'}"),
    # Keifit
    ("{n:'Keifit Moreira Dos Santos',i:'KM',t:1064.0,ds:17,ult:'26/05'}",
     "{n:'Keifit Moreira Dos Santos',i:'KM',t:1089,ds:18,ult:'30/05'}"),
    # Amanda Goulart
    ("{n:'Amanda Goulart Andrade',i:'AG',t:905.0,ds:16,ult:'28/05'}",
     "{n:'Amanda Goulart Andrade',i:'AG',t:945,ds:17,ult:'30/05'}"),
    # Carla Santos
    ("{n:'Carla Santos Luiz',i:'CS',t:761.0,ds:18,ult:'28/05'}",
     "{n:'Carla Santos Luiz',i:'CS',t:821,ds:19,ult:'30/05'}"),
    # Victor Roberto
    ("{n:'Victor Roberto De Oliveira Nascimento',i:'VR',t:960.0,ds:20,ult:'28/05'}",
     "{n:'Victor Roberto De Oliveira Nascimento',i:'VR',t:1600,ds:21,ult:'30/05'}"),
    # Renato
    ("{n:'Renato Lembranci Metzke Junior',i:'RL',t:850.0,ds:13,ult:'27/05'}",
     "{n:'Renato Lembranci Metzke Junior',i:'RL',t:950,ds:14,ult:'30/05'}"),

    # ── Fix barreiras double dias entry ─────────────────────────────────────
    # The dias array has: ...{d:'29/05',ac:4,cel:4},{d:'30/05',ac:4,cel:4},{d:'30/05',ac:3,cel:10}
    # Should be:          ...{d:'29/05',ac:4,cel:4},{d:'30/05',ac:3,cel:10}
    ("{d:'29/05',ac:4,cel:4},{d:'30/05',ac:4,cel:4},{d:'30/05',ac:3,cel:10}",
     "{d:'29/05',ac:4,cel:4},{d:'30/05',ac:3,cel:10}"),
]

for old, new in fixes:
    count = html.count(old)
    if count == 0:
        print(f"WARNING not found: {old!r}")
    else:
        html = html.replace(old, new, 1)
        print(f"OK: replaced {old[:60]!r}...")

with open(INDEX, 'w', encoding='utf-8') as f:
    f.write(html)
print("\nindex.html updated.")
