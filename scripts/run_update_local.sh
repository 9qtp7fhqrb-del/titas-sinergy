#!/bin/bash
# Atualiza D360 direto no Mac, sem GitHub Actions
# Roda a cada 30 min via LaunchAgent (com.titas.d360local)

PROJECT="/Users/marcelolima/Documents/Claude/Projects/titas sinergy"
LOG="$PROJECT/.d360-local.log"
PYTHON=/usr/bin/python3

# PATH completo (garante acesso a node/npm/npx)
export PATH="/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
[ -f "$HOME/.nvm/nvm.sh" ] && source "$HOME/.nvm/nvm.sh" 2>/dev/null

echo "$(date '+%Y-%m-%d %H:%M:%S') — iniciando atualização local" >> "$LOG"

cd "$PROJECT" || exit 1

# Roda o script de atualização (credenciais em ~/Documents/D360-Vendas/.erp-credentials.json)
$PYTHON scripts/update_d360.py >> "$LOG" 2>&1
EXIT=$?

if [ $EXIT -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') — script OK, fazendo deploy..." >> "$LOG"

    # Localiza firebase CLI
    FIREBASE=""
    for p in /usr/local/bin/firebase /opt/homebrew/bin/firebase \
              "$HOME/.npm/bin/firebase" "$HOME/node_modules/.bin/firebase"; do
        [ -x "$p" ] && FIREBASE="$p" && break
    done
    [ -z "$FIREBASE" ] && FIREBASE="npx --yes firebase-tools"

    $FIREBASE deploy --only hosting --project titas-sinergy >> "$LOG" 2>&1
    echo "$(date '+%Y-%m-%d %H:%M:%S') — deploy concluído" >> "$LOG"

    # Sincroniza origin/main via API (evita timeout do git push no arquivo de 2.3MB)
    GITHUB_TOKEN=$(cat "$HOME/.titas_github_token" 2>/dev/null) $PYTHON "$PROJECT/scripts/push_github.py" >> "$LOG" 2>&1
    echo "$(date '+%Y-%m-%d %H:%M:%S') — github sync concluído" >> "$LOG"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') — ERRO no script (exit $EXIT)" >> "$LOG"
fi
