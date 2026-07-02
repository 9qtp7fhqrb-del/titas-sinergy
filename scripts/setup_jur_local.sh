#!/bin/bash
# Setup do cron local de sincronização WhatsApp Jurídico
# Roda uma vez; instala launchd + salva chave de API

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_LABEL="com.titassinergy.jur-sync"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
PYTHON="$(which python3)"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Setup — Jurídico WhatsApp Sync (Titãs Sinergy)    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Chave Anthropic API ──────────────────────────────────
ENV_FILE="$PROJECT_DIR/.env"
if grep -q "ANTHROPIC_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    echo "✔ ANTHROPIC_API_KEY já configurada em .env"
else
    echo "Cole sua chave Anthropic API (começa com sk-ant-):"
    read -r API_KEY
    if [[ -z "$API_KEY" ]]; then
        echo "✗ Chave vazia. Abortando."
        exit 1
    fi
    echo "ANTHROPIC_API_KEY=$API_KEY" >> "$ENV_FILE"
    echo "✔ Chave salva em .env"
fi

# ── 2. Instalar dependência Python ─────────────────────────
echo ""
echo "Instalando anthropic SDK..."
$PYTHON -m pip install anthropic requests -q
echo "✔ Dependências OK"

# ── 3. Criar launchd plist ─────────────────────────────────
echo ""
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$PROJECT_DIR/scripts/jur_whatsapp_sync.py</string>
    </array>

    <!-- Roda a cada 30 minutos -->
    <key>StartInterval</key>
    <integer>1800</integer>

    <!-- Roda também ao carregar (boot/login) -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Reinicia automaticamente se falhar -->
    <key>KeepAlive</key>
    <false/>

    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/.jur-sync.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/.jur-sync.log</string>
</dict>
</plist>
PLIST

echo "✔ LaunchAgent criado em $PLIST_PATH"

# ── 4. Carregar no launchd ─────────────────────────────────
echo ""
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"
echo "✔ LaunchAgent carregado — sync ativo a cada 30 min"

# ── 5. Resumo ──────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  Sync jurídico configurado com sucesso!"
echo ""
echo "  • Roda a cada 30 min enquanto o Mac estiver ligado"
echo "  • Log em: .jur-sync.log"
echo "  • Para parar: launchctl unload $PLIST_PATH"
echo "  • Para ver status: launchctl list | grep jur-sync"
echo "══════════════════════════════════════════════════════"
echo ""
