#!/bin/bash
# ── Titãs Sinergy · Instalador do Auto-Deploy ────────────────────────────

PROJECT="/Users/marcelolima/Documents/Claude/Projects/titas sinergy"
PLIST_SRC="$PROJECT/com.titas.sinergy.autodeploy.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.titas.sinergy.autodeploy.plist"

echo ""
echo "⚡ Configurando Auto-Deploy do Titãs Sinergy..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Permissão de execução
chmod +x "$PROJECT/auto-deploy.sh"

# Para versão anterior
launchctl unload "$PLIST_DST" 2>/dev/null
pkill -f "auto-deploy.sh" 2>/dev/null
sleep 1

# Instala o plist
cp "$PLIST_SRC" "$PLIST_DST"

# Carrega o LaunchAgent
launchctl load "$PLIST_DST"
echo "✅ LaunchAgent instalado e carregado"

# Inicia imediatamente (sem precisar reiniciar)
echo ""
echo "🚀 Iniciando auto-deploy agora..."
nohup /bin/bash "$PROJECT/auto-deploy.sh" \
    &>> "$PROJECT/.auto-deploy.log" &

DPID=$!
sleep 2
if kill -0 "$DPID" 2>/dev/null; then
    echo "✅ Processo iniciado (PID $DPID)"
else
    echo "⚠️  Processo não encontrado — verifique o log"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🟢 Auto-Deploy ATIVO!"
echo ""
echo "   • Publica automaticamente ao salvar index.html"
echo "   • Inicia sozinho ao ligar o Mac"
echo "   • Log: $PROJECT/.auto-deploy.log"
echo ""
echo "   Para parar: pkill -f auto-deploy.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Pressione qualquer tecla para fechar..."
read -n 1
