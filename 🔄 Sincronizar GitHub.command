#!/bin/bash
cd "/Users/marcelolima/Documents/Claude/Projects/titas sinergy"

echo "📡 Buscando alterações do GitHub..."
git pull --rebase origin main 2>&1

echo ""
echo "📦 Enviando alterações locais..."
git add -A
git diff --cached --quiet && echo "✅ Nada a enviar — código já sincronizado." || (
  git commit -m "update: $(TZ=America/Sao_Paulo date +'%d/%m/%Y %H:%M')" && \
  git push origin main && \
  echo "✅ Enviado com sucesso!"
)

echo ""
echo "Pressione qualquer tecla para fechar..."
read -n 1
