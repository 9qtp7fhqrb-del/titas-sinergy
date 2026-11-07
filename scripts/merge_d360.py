#!/usr/bin/env python3
"""
Injeta o bloco 'const D360 = {...}' gerado pelo script de dados
no index.html do remote, preservando todo o código (botões, funções, fixes).
Uso: python3 scripts/merge_d360.py <novo.html> <base.html> <saida.html>
"""
import re, sys

def extract_d360(content):
    m = re.search(r'(^const D360 = \{)', content, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    depth = 0
    i = m.start(1) + len("const D360 = ")
    in_str = False
    str_char = None
    while i < len(content):
        c = content[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == str_char:
                in_str = False
        else:
            if c in '"\'`':
                in_str = True
                str_char = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    if end < len(content) and content[end] == ';':
                        end += 1
                    if end < len(content) and content[end] == '\n':
                        end += 1
                    return (start, end, content[start:end])
        i += 1
    return None

novo_path = sys.argv[1]
base_path = sys.argv[2]
out_path  = sys.argv[3]

with open(novo_path, 'r', encoding='utf-8') as f:
    novo = f.read()
with open(base_path, 'r', encoding='utf-8') as f:
    base = f.read()

novo_block = extract_d360(novo)
base_block = extract_d360(base)

if novo_block and base_block:
    merged = base[:base_block[0]] + novo_block[2] + base[base_block[1]:]
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(merged)
    print('[merge] D360 do script injetado no código do remote — fixes de código preservados')
else:
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(novo)
    print('[merge] fallback: usando gerado pelo script completo')
