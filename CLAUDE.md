# TITÃS SINERGY — Contexto do Projeto

## Stack
- HTML/CSS/JS puro em `index.html` (arquivo único, ~20k linhas)
- Firebase Hosting: https://titas-sinergy.web.app (projeto `titas-sinergy`)
- Firestore para metas, resultados Academy e histórico D360
- Tailwind CDN, Chart.js, jsPDF, Font Awesome

## Estrutura D360 (painel principal)
Objeto `D360` no `index.html` contém:
- `diasDecorridos` — valor **estático** escrito pelo script Python a cada run do GitHub Actions. NUNCA recalcular com `new Date().getDate()` — isso quebra as projeções. `_d360Init()` usa `D360.diasDecorridos = D360.diasDecorridos || Math.min(now.getDate(), D360.diasMes)` (preserva o valor do Python).
- `diasMes` — total de dias do mês, também atualizado pelo Python
- `subredes` — t1 (Talysson), t2 (Adriel), t3 (Arthur)
- `lojas` — 11 lojas com `total`, `ped`, `acessorios`, `top` (vendedores)

### Lojas por subrede
- **T1:** cariacica, itabuna, moxuara, praiadacosta
- **T2:** barreiras, teixeira, laranjeiras
- **T3:** saomateus, serra, montserrat, linhares

---

## Atualização Diária de Vendas — REGRAS OBRIGATÓRIAS

Marcelo envia 2 PDFs do ERP CDC diariamente:
1. **Relatório de Vendas por Colaborador** — dados individuais
2. **Relatório Gráfico** — totais por loja (ground truth para conferência)

### Regra principal: ignorar SBON de Gerentes/Subgerentes
No Relatório por Colaborador, Gerentes e Subgerentes aparecem com o **total da loja atribuído a eles**. Esses valores DEVEM SER EXCLUÍDOS.

**Incluir apenas:** Perfil = **Vendedor**
**Excluir:** Gerente, Subgerente, Trainee (Trainee não entra no total da loja)

**Exceção dupla entrada:** Quando Gerente/Subgerente aparece DUAS VEZES (uma como Gerente com total da loja, outra como Vendedor com vendas pessoais), usar SOMENTE a entrada de Vendedor.
- Exemplos confirmados: Wilghyner (Teixeira), Krystian (Linhares), Juliana (São Mateus), Renato (Praia da Costa)

### Caso especial Moxuara — Gabriel Barreto Pereira
Gabriel aparece 3x no ERP para Shopping Moxuara:
1. **Subgerente** (mesmo valor que Gerente Ana Carolina) → EXCLUIR
2. **Gerente** (valor diferente) → EXCLUIR também (outra atribuição de gestão)
3. **Vendedor** (valor pequeno, só acessórios) → INCLUIR

Total Moxuara = Khayllane + Iasmim + Luccas + Gabriel(Vendedor) — confirmado pelo Relatório Gráfico.

### Acessórios
- Usar coluna ACESSÓRIOS do Relatório por Colaborador
- Só contar ACESSÓRIOS de Vendedores (não de Gerentes/Subgerentes)
- O ACESS do Gerente/Subgerente confirma o total mas não se adiciona

### Campos a ignorar
- Posição, Qtd Vendas, % do Total
- Seções VENDAS POR PERFIL e VENDAS POR GRUPO DE PRODUTO
- Grupo BONIFICADO não alimenta o campo de acessórios

### Conferência
- Receita bruta do Relatório Gráfico = total correto de cada loja
- Se D360 ≠ Relatório Gráfico → identificar qual entrada de gestão foi incluída erroneamente

### Tipo de operação
- PDF com período de **1 dia** → SOMAR ao D360 existente
- PDF com período **acumulado** (ex: 01/06 a 07/06) → SUBSTITUIR totais do D360

---

## Deploy
```bash
firebase deploy --only hosting          # publica o site
firebase deploy --only firestore:rules  # publica regras Firestore
```

### Auto-deploy (background)
Script `auto-deploy.sh` monitora `index.html` e `firestore.rules` a cada 4s.
- Iniciar: duplo clique em `⚡ Ativar Auto-Deploy.command`
- **Problema:** firebase não encontrado no PATH do nohup — verificar com `which firebase`
- Log: `.auto-deploy.log`

---

## Regras de negócio implementadas

### Lançamento de metas mensais
- Coleção Firestore: `ts_d360_historico`, doc ID: `metas_YYYY_MM`
- **Regra 24h:** após lançamento, gerente pode editar por 24h. Depois, só o Diretor pode alterar
- Diretor vê botão "Zerar" em cada loja para permitir novo lançamento

### Cargos com acesso ao botão de metas
diretoria, franqueado, gerente-senior, gerente-senior-acess, gerente, subgerente

### Equipe por loja (`_EQUIPE` no código)
Lista de nomes completos de cada loja — usada para exibir todos os colaboradores no ranking mesmo sem vendas no dia.

---

## Preferências de desenvolvimento
- Respostas concisas e diretas
- Não usar bullet points excessivos
- Criar/editar arquivos diretamente (não mostrar código para copiar)
- Sempre publicar após alterações (auto-deploy ou firebase deploy)
- Seguir instruções do projeto em português
