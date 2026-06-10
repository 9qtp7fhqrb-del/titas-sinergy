#!/bin/bash
# ── Titãs Sinergy · Auto-Deploy (rodando em background) ──────────────────

# Carrega o PATH completo do usuário (zsh/bash)
export PATH="/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
[ -f "$HOME/.zshrc"        ] && source "$HOME/.zshrc"        2>/dev/null
[ -f "$HOME/.bash_profile" ] && source "$HOME/.bash_profile" 2>/dev/null
[ -f "$HOME/.nvm/nvm.sh"   ] && source "$HOME/.nvm/nvm.sh"   2>/dev/null

PROJECT="/Users/marcelolima/Documents/Claude/Projects/titas sinergy"
LOG="$PROJECT/.auto-deploy.log"
LOCK="$PROJECT/.auto-deploy.pid"

# Evita instâncias duplicadas
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "[$(date '+%H:%M:%S')] já existe uma instância rodando (PID $(cat "$LOCK"))" >> "$LOG"
    exit 0
fi
echo $$ > "$LOCK"
trap "rm -f '$LOCK'" EXIT

cd "$PROJECT" || exit 1

# Localiza o firebase CLI
FIREBASE=""
for p in \
    /usr/local/bin/firebase \
    /opt/homebrew/bin/firebase \
    "$HOME/.npm/bin/firebase" \
    "$HOME/node_modules/.bin/firebase"; do
    [ -x "$p" ] && FIREBASE="$p" && break
done
# Fallback: npx
[ -z "$FIREBASE" ] && FIREBASE="npx --yes firebase-tools"

echo "" >> "$LOG"
echo "[$(date '+%d/%m %H:%M:%S')] ✅ Auto-Deploy iniciado (PID $$) · firebase: $FIREBASE" >> "$LOG"

H_LAST=$(md5 -q "$PROJECT/index.html"       2>/dev/null)
R_LAST=$(md5 -q "$PROJECT/firestore.rules"  2>/dev/null)

_deploy() {
    local targets="$1"
    echo "[$(date '+%d/%m %H:%M:%S')] 📝 Alteração detectada — publicando $targets..." >> "$LOG"
    $FIREBASE deploy --only "$targets" >> "$LOG" 2>&1 \
        && echo "[$(date '+%d/%m %H:%M:%S')] ✅ Deploy concluído: https://titas-sinergy.web.app" >> "$LOG" \
        || echo "[$(date '+%d/%m %H:%M:%S')] ❌ Erro no deploy — verifique o log acima" >> "$LOG"
}

while true; do
    H_NEW=$(md5 -q "$PROJECT/index.html"      2>/dev/null)
    R_NEW=$(md5 -q "$PROJECT/firestore.rules" 2>/dev/null)
    TARGETS=""
    [ "$H_NEW" != "$H_LAST" ] && TARGETS="hosting"
    [ "$R_NEW" != "$R_LAST" ] && {
        [ -n "$TARGETS" ] && TARGETS="$TARGETS,firestore:rules" || TARGETS="firestore:rules"
    }
    if [ -n "$TARGETS" ]; then
        H_LAST="$H_NEW"; R_LAST="$R_NEW"
        _deploy "$TARGETS"
    fi
    sleep 4
done
