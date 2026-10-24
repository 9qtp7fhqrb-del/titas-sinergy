#!/usr/bin/env python3
"""
push_github.py — envia arquivos para o GitHub via API.
Substitui `git push origin main --force` que trava no arquivo de 2.3 MB.

Para index.html usa merge inteligente:
  - busca o conteúdo ATUAL do remote
  - extrai apenas o bloco `const D360 = {...};` do arquivo LOCAL (recém atualizado)
  - injeta esse bloco no remote (preservando todos os fixes de código)
  - sobe o resultado

Para update_d360.py e demais arquivos envia o local diretamente.

Uso:
    python3 scripts/push_github.py
    python3 scripts/push_github.py --file index.html
    python3 scripts/push_github.py --all
"""

import argparse, base64, json, os, re, subprocess, sys, urllib.request, urllib.error

def _load_token():
    t = os.environ.get("GITHUB_TOKEN", "")
    if t:
        return t
    token_file = os.path.expanduser("~/.titas_github_token")
    if os.path.exists(token_file):
        return open(token_file).read().strip()
    print("[ERRO] Token não encontrado. Defina GITHUB_TOKEN ou crie ~/.titas_github_token")
    sys.exit(1)

TOKEN = _load_token()
REPO  = os.environ.get("GITHUB_REPO", "9qtp7fhqrb-del/titas-sinergy")
ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES_DEFAULT = ["index.html", "scripts/update_d360.py"]

def api(method, path, data=None, timeout=120):
    url = f"https://api.github.com/repos/{REPO}/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"token {TOKEN}", "Content-Type": "application/json"},
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[ERRO] {method} {path} → HTTP {e.code}: {e.read().decode()[:200]}")
        sys.exit(1)

def get_remote_content(path):
    """Busca o conteúdo atual do arquivo no remote (base64 → str)."""
    try:
        result = api("GET", f"contents/{path}")
        return base64.b64decode(result["content"]).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [AVISO] não foi possível buscar {path} do remote: {e}")
        return None

def extract_d360_block(content):
    """
    Extrai o bloco `const D360 = { ... };` do conteúdo.
    Retorna (start_idx, end_idx, bloco_str) ou None se não encontrar.
    """
    m = re.search(r'(^const D360 = \{)', content, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    # Percorre caractere a caractere contando chaves para achar o fechamento
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
            if c in ('"', "'", '`'):
                in_str = True
                str_char = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    # Consome ';' e '\n' opcionais após '}'
                    if end < len(content) and content[end] == ';':
                        end += 1
                    if end < len(content) and content[end] == '\n':
                        end += 1
                    return (start, end, content[start:end])
        i += 1
    return None

def merge_index_html(local_content, remote_content):
    """
    Substitui o bloco D360 no remote pelo bloco D360 do local.
    Se não conseguir extrair/substituir, retorna o local (fallback).
    """
    local_block = extract_d360_block(local_content)
    remote_block = extract_d360_block(remote_content)

    if not local_block or not remote_block:
        print("  [merge] não foi possível extrair bloco D360 — usando local completo (fallback)")
        return local_content

    local_d360_str  = local_block[2]
    r_start, r_end, _ = remote_block

    merged = remote_content[:r_start] + local_d360_str + remote_content[r_end:]
    print(f"  [merge] D360 do local ({len(local_d360_str):,} chars) injetado no remote ({len(remote_content):,} chars) → {len(merged):,} chars")
    return merged

def upload_blob(local_path, content_override=None):
    """Cria um blob no GitHub. content_override (bytes) substitui o arquivo local."""
    abs_path = os.path.join(ROOT, local_path)
    if content_override is not None:
        data = content_override
        size_kb = len(data) // 1024
    elif os.path.exists(abs_path):
        with open(abs_path, "rb") as f:
            data = f.read()
        size_kb = os.path.getsize(abs_path) // 1024
    else:
        print(f"[AVISO] arquivo não encontrado: {abs_path}")
        return None

    print(f"  enviando blob: {local_path} ({size_kb} KB)...", end=" ", flush=True)
    content_b64 = base64.b64encode(data).decode()
    result = api("POST", "git/blobs", {"content": content_b64, "encoding": "base64"}, timeout=180)
    sha = result["sha"]
    print(sha[:12])
    return {"path": local_path, "mode": "100644", "type": "blob", "sha": sha}

def get_commit_message():
    try:
        msg = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
        return msg or "data: vendas"
    except Exception:
        return "data: vendas"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="arquivo relativo ao repositório (ex: index.html)")
    parser.add_argument("--all", action="store_true", help="envia todos os arquivos padrão")
    args = parser.parse_args()

    files_to_push = [args.file] if args.file else FILES_DEFAULT

    print(f"[push_github] repo: {REPO}")

    # HEAD do main remoto
    ref      = api("GET", "git/ref/heads/main")
    sha_head = ref["object"]["sha"]
    print(f"  HEAD main: {sha_head[:12]}")

    commit   = api("GET", f"git/commits/{sha_head}")
    sha_tree = commit["tree"]["sha"]
    print(f"  tree:      {sha_tree[:12]}")

    # Blobs — index.html usa merge, demais sobem direto
    tree_entries = []
    for f in files_to_push:
        abs_path = os.path.join(ROOT, f)
        if not os.path.exists(abs_path):
            print(f"[AVISO] arquivo não encontrado: {abs_path}")
            continue

        if f == "index.html":
            with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                local_content = fh.read()
            print(f"  buscando index.html do remote para merge...")
            remote_content = get_remote_content("index.html")
            if remote_content:
                final_content = merge_index_html(local_content, remote_content)
            else:
                print("  [merge] remote indisponível — usando local completo")
                final_content = local_content
            entry = upload_blob(f, final_content.encode("utf-8"))
        else:
            entry = upload_blob(f)

        if entry:
            tree_entries.append(entry)

    if not tree_entries:
        print("[AVISO] nenhum arquivo enviado.")
        sys.exit(0)

    # Nova tree sobre o HEAD remoto (não força)
    new_tree = api("POST", "git/trees", {"base_tree": sha_tree, "tree": tree_entries})
    print(f"  nova tree: {new_tree['sha'][:12]}")

    # Novo commit com o HEAD remoto como pai
    msg = get_commit_message()
    new_commit = api("POST", "git/commits", {
        "message": msg,
        "tree": new_tree["sha"],
        "parents": [sha_head]
    })
    print(f"  commit:    {new_commit['sha'][:12]}  \"{msg}\"")

    # Atualiza ref (force=True necessário pois HEAD local pode divergir)
    result = api("PATCH", "git/refs/heads/main", {"sha": new_commit["sha"], "force": True})
    print(f"  main →     {result['object']['sha'][:12]}")
    print("[OK] push concluído via API GitHub.")

if __name__ == "__main__":
    main()
