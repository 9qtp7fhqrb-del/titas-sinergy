#!/usr/bin/env python3
"""
push_github.py — envia index.html e scripts/update_d360.py para o GitHub via API.
Substitui `git push origin main --force` que trava no arquivo de 2.3 MB.

Uso:
    python3 scripts/push_github.py
    python3 scripts/push_github.py --file index.html
    python3 scripts/push_github.py --all   (index.html + update_d360.py)
"""

import argparse, base64, json, os, subprocess, sys, urllib.request, urllib.error

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

def upload_blob(local_path):
    abs_path = os.path.join(ROOT, local_path)
    if not os.path.exists(abs_path):
        print(f"[AVISO] arquivo não encontrado: {abs_path}")
        return None
    print(f"  enviando blob: {local_path} ({os.path.getsize(abs_path)//1024} KB)...", end=" ", flush=True)
    with open(abs_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
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
        return msg or "chore: sync via API"
    except Exception:
        return "chore: sync via API"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="arquivo relativo ao repositório (ex: index.html)")
    parser.add_argument("--all", action="store_true", help="envia todos os arquivos padrão")
    args = parser.parse_args()

    if args.file:
        files_to_push = [args.file]
    else:
        files_to_push = FILES_DEFAULT

    print(f"[push_github] repo: {REPO}")

    # HEAD do main
    ref    = api("GET", "git/ref/heads/main")
    sha_head = ref["object"]["sha"]
    print(f"  HEAD main: {sha_head[:12]}")

    commit = api("GET", f"git/commits/{sha_head}")
    sha_tree = commit["tree"]["sha"]
    print(f"  tree:      {sha_tree[:12]}")

    # Blobs
    tree_entries = []
    for f in files_to_push:
        entry = upload_blob(f)
        if entry:
            tree_entries.append(entry)

    if not tree_entries:
        print("[AVISO] nenhum arquivo enviado.")
        sys.exit(0)

    # Nova tree
    new_tree = api("POST", "git/trees", {"base_tree": sha_tree, "tree": tree_entries})
    print(f"  nova tree: {new_tree['sha'][:12]}")

    # Novo commit
    msg = get_commit_message()
    new_commit = api("POST", "git/commits", {
        "message": msg,
        "tree": new_tree["sha"],
        "parents": [sha_head]
    })
    print(f"  commit:    {new_commit['sha'][:12]}  \"{msg}\"")

    # Atualiza ref
    result = api("PATCH", "git/refs/heads/main", {"sha": new_commit["sha"], "force": True})
    print(f"  main →     {result['object']['sha'][:12]}")
    print("[OK] push concluído via API GitHub.")

if __name__ == "__main__":
    main()
