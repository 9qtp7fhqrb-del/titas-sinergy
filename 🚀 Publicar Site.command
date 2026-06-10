#!/bin/bash

# Titãs Sinergy — Deploy Firebase Hosting
cd "/Users/marcelolima/Documents/Claude/Projects/titas sinergy"

echo ""
echo "🚀 Iniciando publicação do Titãs Sinergy..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

npx firebase-tools deploy --only hosting

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Site publicado em: https://titas-sinergy.web.app"
echo ""
echo "Pressione qualquer tecla para fechar..."
read -n 1
