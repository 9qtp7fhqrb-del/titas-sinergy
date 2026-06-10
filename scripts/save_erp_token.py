#!/usr/bin/env python3
"""
Salva o token ERP como variável do repositório GitHub.
Chamado pelo GitHub Actions após novo login.
"""
import json, subprocess, os, sys

token_file = os.environ.get('ERP_TOKEN_OUTPUT', '/tmp/erp_new_token.txt')
if not os.path.exists(token_file):
    print("Sem token novo para salvar")
    sys.exit(0)

token = open(token_file).read().strip()
if not token:
    print("Arquivo de token vazio, ignorando")
    sys.exit(0)

repo    = os.environ.get('GITHUB_REPOSITORY', '')
pat     = os.environ.get('GH_PAT', '')
if not repo or not pat:
    print("GITHUB_REPOSITORY ou GH_PAT não definidos, pulando cache")
    sys.exit(0)

base_url    = f"https://api.github.com/repos/{repo}/actions/variables"
var_url     = f"{base_url}/ERP_TOKEN_CACHE"
headers     = ['-H', f'Authorization: token {pat}', '-H', 'Content-Type: application/json']
payload     = json.dumps({"name": "ERP_TOKEN_CACHE", "value": token})

# Verifica se variável já existe (GET)
r = subprocess.run(
    ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}'] + headers + [var_url],
    capture_output=True, text=True)
status = r.stdout.strip()

if status == '200':
    # Variável existe → atualiza com PATCH na URL com nome
    method, url = 'PATCH', var_url
else:
    # Variável não existe → cria com POST na URL base (sem nome)
    method, url = 'POST', base_url

r2 = subprocess.run(
    ['curl', '-s', '-X', method] + headers + [url, '-d', payload],
    capture_output=True, text=True)

print(f"Token salvo ({method}, status GET: {status})")
if r2.stdout:
    print(r2.stdout[:200])
