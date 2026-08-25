#!/usr/bin/env python3
"""
Auto-diagnóstico Titãs Sinergy
Lê folhas de atendimento novas do WhatsApp e atualiza Firestore.
Roda automaticamente ao abrir o Mac via LaunchAgent.
"""
import os, sys, json, sqlite3, base64, urllib.request, urllib.error
import datetime, time
from pathlib import Path

# ═══════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════
WA_DB   = Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
WA_ROOT = Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/Message"
GRUPO_ID  = 18   # GERENTES REDE TITÃS (ABERTURA)
FIREBASE_CONFIG = Path.home() / ".config/configstore/firebase-tools.json"
ANTHROPIC_KEY_FILE = Path.home() / ".titas_anthropic_key"
STATE_FILE = Path.home() / ".titas_diag_state.json"
LOG_FILE   = Path(__file__).parent.parent / ".diag-auto.log"
FIREBASE_PROJECT = "titas-sinergy"
FIRESTORE_BASE   = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents"

# Horário de corte por dia da semana (hora BRT a partir da qual contam folhas "do dia")
CUTOFF_HOURS = {
    0: 18, 1: 18, 2: 18, 3: 18, 4: 18,  # Seg-Sex: 18h
    5: 13,                                # Sáb: 13h
    6: 20,                                # Dom: 20h
}

# Offset para converter timestamp local em UTC (BRT = UTC-3)
BRT_OFFSET_HOURS = -3

# Todas as lojas ativas
ALL_LOJAS = [
    "barreiras", "cariacica", "itabuna", "laranjeiras", "linhares",
    "montserrat", "moxuara", "praiadacosta", "saomateus", "serra", "teixeira",
]

# Mapeamento gerente sênior → subredes
SUBREDES = {
    "t1": {"nome": "Titãs 1", "gestor": "Talysson", "lojas": ["cariacica", "itabuna", "moxuara", "praiadacosta"]},
    "t2": {"nome": "Titãs 2", "gestor": "Adriel",   "lojas": ["barreiras", "teixeira", "laranjeiras", "praiadacosta"]},
    "t3": {"nome": "Titãs 3", "gestor": "Arthur",   "lojas": ["saomateus", "linhares", "serra", "montserrat"]},
}

PROMPT_IDENTIFICAR = """Você está analisando imagens de folhas de controle de atendimento de lojas de celulares.

TAREFA: Identifique se esta imagem É uma folha de atendimento. Se for, extraia os dados.

IDENTIFICAÇÃO DAS LOJAS (marcadores visuais):
- barreiras: prancheta com clipe marcado "BACCHI" ou "BACURT" + cordão amarelo
- cariacica: texto no rodapé "Abençoado será o novo dia! Chuva de vendas hoje!" OU vendedores Sophia/Roberta/Fabiano
- itabuna: adesivo NOVACRIL ou EUCATEX na prancheta. Vendedores: Andreza, Mikaelle, Thaumatos, Katt Santos
- laranjeiras: prancheta preta + frase "Bom/Boa [hora] ♥ com Jesus!" OU vendedores Lidia, Mayane, Nycally
- linhares: frase "Que Deus nos Abençoe Hoje e Sempre" OU vendedor "Layca"
- montserrat: frase "Bom dia Montserrat" OU vendedores Vinicius, Adriano, Joaquin, Beatriz
- moxuara: prancheta com "Ana ♥ Te Adoramos" + coluna DATA. Vendedores: Luccas, Jasmim, Khayllane
- praiadacosta: prancheta enferrujada com FITA AZUL no clipe + coluna DATA
- saomateus: coraçõezinhos rosas ♡ desenhados no topo da folha
- serra: prancheta com "KARELI" escrito. Vendedores: Gabriel, Luiz G, Luiz H, Beatriz
- teixeira: prancheta enferrujada marrom SEM fita. Vendedores: Mateus, Victor, Isabella, Paloma, Carla, Larisse

COMO CONTAR:
- Cada linha = 1 atendimento
- Coluna V/NV: V = venda de celular, NV = não-venda
- NÃO contar a coluna de acessórios separada
- Rodapé com tentativas ODRES/PayJoy/BNDES = NÃO contar como NV principal
- Se "AP XX%" estiver escrito em grande = confirma a taxa de conversão

RESPONDA APENAS com JSON válido, sem texto adicional:
{
  "e_folha": true/false,
  "loja": "key da loja ou null",
  "total_clientes": N,
  "total_vendas": V,
  "taxa_conversao": X.X,
  "motivos_nv": {"pesquisando": N, "sem_entrada": N, "credito": N, "sem_limite": N, "retorno": N, "outros": N},
  "confianca": "alta/media/baixa",
  "observacoes": "texto opcional"
}

Se NÃO for folha de atendimento (selfie, foto de produto, etc.), responda:
{"e_folha": false, "loja": null}"""


# ═══════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════
def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def notificar_mac(titulo, mensagem):
    msg_escaped = mensagem.replace('"', '\\"').replace("'", "\\'")
    os.system(f'osascript -e \'display notification "{msg_escaped}" with title "{titulo}" sound name "Ping"\'')

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"processed_ids": [], "last_run": None}

def save_state(state):
    try:
        # Manter apenas últimos 500 IDs para não inflar o arquivo
        if len(state.get("processed_ids", [])) > 500:
            state["processed_ids"] = state["processed_ids"][-500:]
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log(f"WARN: Não salvou estado — {e}")

def get_firebase_token():
    npx = Path.home() / ".npm/_npx/7750544ccf494d8b/node_modules/.bin/firebase"
    if npx.exists():
        os.system(f"{npx} projects:list > /dev/null 2>&1")
    with open(FIREBASE_CONFIG) as f:
        return json.load(f)["tokens"]["access_token"]

def firestore_patch(doc_path, doc):
    token = get_firebase_token()
    url = f"{FIRESTORE_BASE}/{doc_path}"
    req = urllib.request.Request(url, data=json.dumps(doc).encode(), method="PATCH")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)

def firestore_get(doc_path):
    token = get_firebase_token()
    url = f"{FIRESTORE_BASE}/{doc_path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# ═══════════════════════════════════════════════
# JANELA DE TEMPO RELEVANTE
# ═══════════════════════════════════════════════
def janela_relevante():
    """
    Retorna (date_str, cocoa_inicio, cocoa_fim) da janela principal de folhas.
    Se for antes do cutoff de hoje, usa ontem.
    Retorna também shopping_cutoff (cocoa) para folhas de shopping (após 22h).
    """
    agora = datetime.datetime.now()
    weekday = agora.weekday()  # 0=Seg, 5=Sab, 6=Dom
    cutoff = CUTOFF_HOURS.get(weekday, 18)

    if agora.hour < cutoff:
        # Ainda não chegou o horário — usar ontem
        data = (agora - datetime.timedelta(days=1)).date()
        weekday_ontem = data.weekday()
        cutoff = CUTOFF_HOURS.get(weekday_ontem, 18)
    else:
        data = agora.date()

    # Converter BRT → UTC → Cocoa (segundos desde 2001-01-01)
    COCOA_EPOCH = datetime.datetime(2001, 1, 1)
    dt_inicio_utc = datetime.datetime(data.year, data.month, data.day, cutoff, 0, 0) - datetime.timedelta(hours=BRT_OFFSET_HOURS)
    dt_fim_utc    = datetime.datetime(data.year, data.month, data.day, 23, 59, 59) - datetime.timedelta(hours=BRT_OFFSET_HOURS)

    cocoa_inicio = (dt_inicio_utc - COCOA_EPOCH).total_seconds()
    cocoa_fim    = (dt_fim_utc    - COCOA_EPOCH).total_seconds()

    # Shopping: após 22h BRT (incluindo virada para o dia seguinte)
    dt_shopping_utc = datetime.datetime(data.year, data.month, data.day, 22, 0, 0) - datetime.timedelta(hours=BRT_OFFSET_HOURS)
    cocoa_shopping  = (dt_shopping_utc - COCOA_EPOCH).total_seconds()

    return data.strftime("%Y-%m-%d"), cocoa_inicio, cocoa_fim, cocoa_shopping


# ═══════════════════════════════════════════════
# WHATSAPP — BUSCAR IMAGENS NOVAS
# ═══════════════════════════════════════════════
def buscar_imagens_novas(cocoa_inicio, cocoa_fim, processed_ids):
    """Retorna lista de (media_pk, cocoa_ts, local_path, caption) da janela."""
    if not WA_DB.exists():
        log("ERRO: Banco WhatsApp não encontrado. WhatsApp Desktop instalado?")
        return []

    conn = sqlite3.connect(str(WA_DB))
    cur  = conn.cursor()

    query = """
        SELECT mi.Z_PK, m.ZMESSAGEDATE, mi.ZMEDIALOCALPATH, m.ZTEXT
        FROM ZWAMESSAGE m
        LEFT JOIN ZWAMEDIAITEM mi ON m.ZMEDIAITEM = mi.Z_PK
        WHERE m.ZCHATSESSION = ?
          AND mi.ZMEDIALOCALPATH IS NOT NULL
          AND m.ZMESSAGEDATE >= ?
          AND m.ZMESSAGEDATE <= ?
          AND (
              mi.ZMEDIALOCALPATH LIKE '%.jpg' OR
              mi.ZMEDIALOCALPATH LIKE '%.jpeg' OR
              mi.ZMEDIALOCALPATH LIKE '%.png' OR
              mi.ZMEDIALOCALPATH LIKE '%.webp'
          )
        ORDER BY m.ZMESSAGEDATE
    """

    cur.execute(query, (GRUPO_ID, cocoa_inicio, cocoa_fim))
    rows = cur.fetchall()
    conn.close()

    novas = []
    for media_pk, cocoa_ts, rel_path, caption in rows:
        if media_pk in processed_ids:
            continue
        full_path = WA_ROOT / rel_path
        if full_path.exists():
            novas.append((media_pk, cocoa_ts, str(full_path), caption or ""))

    return novas


# ═══════════════════════════════════════════════
# CLAUDE API — IDENTIFICAR FOLHA
# ═══════════════════════════════════════════════
def identificar_folha(image_path):
    """Chama Claude claude-haiku-4-5 vision para identificar loja e contar V/NV."""
    if not ANTHROPIC_KEY_FILE.exists():
        raise FileNotFoundError(
            f"Chave API Anthropic não encontrada.\n"
            f"Crie o arquivo: {ANTHROPIC_KEY_FILE}\n"
            f"Conteúdo: sua chave API começando com 'sk-ant-...'"
        )

    api_key = ANTHROPIC_KEY_FILE.read_text().strip()

    # Detectar tipo de imagem
    ext = image_path.lower().rsplit(".", 1)[-1]
    media_type_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    media_type = media_type_map.get(ext, "image/jpeg")

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 600,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": img_b64}
                },
                {"type": "text", "text": PROMPT_IDENTIFICAR}
            ]
        }]
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        method="POST"
    )
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")

    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)

    text = resp["content"][0]["text"].strip()

    # Extrair JSON da resposta
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    return json.loads(text)


# ═══════════════════════════════════════════════
# FIRESTORE — SALVAR DIAGNÓSTICO
# ═══════════════════════════════════════════════
def salvar_diagnostico(loja_key, date_str, dados, ts_str):
    """Salva doc diário e atualiza mensal."""
    mes = date_str[:7].replace("-", "_")  # "2026_08"

    motivos_fields = {
        k: {"integerValue": str(v)}
        for k, v in dados.get("motivos_nv", {}).items() if v > 0
    }

    doc_diario = {"fields": {
        "loja":               {"stringValue": loja_key},
        "data":               {"stringValue": date_str},
        "ultima_atualizacao": {"stringValue": ts_str},
        "analise": {"mapValue": {"fields": {
            "total_clientes":  {"integerValue": str(dados["total_clientes"])},
            "total_vendas":    {"integerValue": str(dados["total_vendas"])},
            "taxa_conversao":  {"doubleValue":  float(dados["taxa_conversao"])},
            "motivos_nv":      {"mapValue": {"fields": motivos_fields}},
            "padrao":          {"stringValue": dados.get("observacoes", "")},
            "recomendacoes":   {"stringValue": "Gerado automaticamente."},
        }}}
    }}

    log(f"    → Salvando diário {loja_key}_{date_str}")
    firestore_patch(f"ts_diagnostico/{loja_key}_{date_str}", doc_diario)

    # Mensal
    existing = firestore_get(f"ts_diagnostico/{loja_key}_mensal_{mes}")
    if existing:
        fld = existing.get("fields", {})
        dias_list = [x["stringValue"] for x in fld.get("dias_com_dado", {}).get("arrayValue", {}).get("values", [])]
        if date_str in dias_list:
            log(f"    → Mensal {loja_key}: {date_str} já contabilizado")
            return
        tc   = int(fld.get("total_clientes", {}).get("integerValue", 0))
        tv   = int(fld.get("total_vendas",   {}).get("integerValue", 0))
        dias = int(fld.get("dias",           {}).get("integerValue", 0))
        motivos_acc = {k: int(v.get("integerValue", 0)) for k, v in fld.get("motivos_nv", {}).get("mapValue", {}).get("fields", {}).items()}
    else:
        tc, tv, dias, dias_list, motivos_acc = 0, 0, 0, [], {}

    tc   += dados["total_clientes"]
    tv   += dados["total_vendas"]
    dias += 1
    dias_list.append(date_str)
    for k, v in dados.get("motivos_nv", {}).items():
        if v > 0:
            motivos_acc[k] = motivos_acc.get(k, 0) + v

    taxa_mensal = round(tv / tc * 100, 1) if tc else 0
    doc_mensal  = {"fields": {
        "loja":               {"stringValue": loja_key},
        "mes":                {"stringValue": mes},
        "ultima_atualizacao": {"stringValue": ts_str},
        "total_clientes":     {"integerValue": str(tc)},
        "total_vendas":       {"integerValue": str(tv)},
        "taxa_conversao":     {"doubleValue":  taxa_mensal},
        "dias":               {"integerValue": str(dias)},
        "dias_com_dado":      {"arrayValue": {"values": [{"stringValue": d} for d in sorted(dias_list)]}},
        "motivos_nv":         {"mapValue": {"fields": {k: {"integerValue": str(v)} for k, v in motivos_acc.items()}}},
    }}

    log(f"    → Atualizando mensal {loja_key}_mensal_{mes}")
    firestore_patch(f"ts_diagnostico/{loja_key}_mensal_{mes}", doc_mensal)


# ═══════════════════════════════════════════════
# FIRESTORE — SALVAR STATUS DE NOTIFICAÇÕES
# ═══════════════════════════════════════════════
def salvar_status_notificacoes(date_str, lojas_enviaram, cocoa_shopping):
    """
    Salva quais lojas enviaram folhas hoje.
    Campo `shopping_ok` = lojas com folha após 22h.
    """
    agora_cocoa = (datetime.datetime.utcnow() - datetime.datetime(2001, 1, 1)).total_seconds()
    janela_shopping_aberta = agora_cocoa >= cocoa_shopping

    doc = {"fields": {
        "data":            {"stringValue": date_str},
        "atualizado_em":   {"stringValue": datetime.datetime.now().isoformat()},
        "janela_shopping":  {"booleanValue": janela_shopping_aberta},
    }}

    for loja in ALL_LOJAS:
        enviou = loja in lojas_enviaram
        doc["fields"][loja] = {"booleanValue": enviou}

    firestore_patch(f"ts_notificacoes/status_{date_str}", doc)
    log(f"  → Notificações salvas para {date_str}: {len(lojas_enviaram)}/{len(ALL_LOJAS)} lojas")


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
def main():
    log("=" * 50)
    log("Auto-diagnóstico iniciado")

    # Verificar chave Anthropic
    if not ANTHROPIC_KEY_FILE.exists():
        msg = f"Configure sua chave API Anthropic em {ANTHROPIC_KEY_FILE}"
        log(f"ERRO: {msg}")
        notificar_mac("Titãs Diagnóstico — Configuração", msg)
        return 1

    # Verificar WhatsApp DB
    if not WA_DB.exists():
        log("ERRO: Banco WhatsApp não encontrado. WhatsApp Desktop precisa estar instalado.")
        return 1

    # Carregar estado
    state = load_state()
    processed_ids = set(state.get("processed_ids", []))

    # Calcular janela relevante
    date_str, cocoa_inicio, cocoa_fim, cocoa_shopping = janela_relevante()
    log(f"Janela: {date_str} | Buscando {len(processed_ids)} IDs já processados")

    # Buscar imagens novas
    imagens = buscar_imagens_novas(cocoa_inicio, cocoa_fim, processed_ids)
    log(f"Imagens novas encontradas: {len(imagens)}")

    if not imagens:
        log("Nenhuma imagem nova para processar.")
        # Mesmo sem novas imagens, atualiza status de notificações
        existing_enviaram = set()
        try:
            doc_status = firestore_get(f"ts_notificacoes/status_{date_str}")
            if doc_status:
                flds = doc_status.get("fields", {})
                existing_enviaram = {l for l in ALL_LOJAS if flds.get(l, {}).get("booleanValue") is True}
        except Exception:
            pass
        try:
            salvar_status_notificacoes(date_str, existing_enviaram, cocoa_shopping)
        except Exception as e:
            log(f"WARN: Não atualizou status — {e}")
        return 0

    # Processar cada imagem
    ts_str = datetime.datetime.now().isoformat()
    lojas_processadas = {}   # loja_key → dados
    novos_ids = []
    erros = 0

    for media_pk, cocoa_ts, img_path, caption in imagens:
        log(f"  Analisando: {Path(img_path).name} [{caption[:40] if caption else '—'}]")
        try:
            resultado = identificar_folha(img_path)
        except Exception as e:
            log(f"    ✗ Erro Claude API: {e}")
            erros += 1
            novos_ids.append(media_pk)  # Marcar como visto para não re-tentar sempre
            continue

        novos_ids.append(media_pk)

        if not resultado.get("e_folha"):
            log(f"    → Não é folha (selfie/outro)")
            continue

        loja = resultado.get("loja")
        if not loja or loja not in ALL_LOJAS:
            conf = resultado.get("confianca", "?")
            log(f"    → Loja não identificada (confiança: {conf}): {resultado.get('observacoes','')}")
            continue

        log(f"    ✓ {loja}: {resultado.get('total_vendas')}/{resultado.get('total_clientes')} "
            f"({resultado.get('taxa_conversao')}%) confiança={resultado.get('confianca')}")

        # Se a mesma loja aparecer mais de uma vez (duas equipes), somar
        if loja in lojas_processadas:
            prev = lojas_processadas[loja]
            resultado["total_clientes"] += prev["total_clientes"]
            resultado["total_vendas"]   += prev["total_vendas"]
            for k, v in prev.get("motivos_nv", {}).items():
                resultado["motivos_nv"][k] = resultado["motivos_nv"].get(k, 0) + v
            tc = resultado["total_clientes"]
            resultado["taxa_conversao"] = round(resultado["total_vendas"] / tc * 100, 1) if tc else 0
            log(f"    → Acumulado (2ª equipe): {resultado['total_vendas']}/{resultado['total_clientes']}")

        lojas_processadas[loja] = resultado

        # Salvar no Firestore
        try:
            salvar_diagnostico(loja, date_str, resultado, ts_str)
        except Exception as e:
            log(f"    ✗ Erro ao salvar Firestore: {e}")

    # Buscar quais lojas já tinham folha antes desta execução
    try:
        doc_status = firestore_get(f"ts_notificacoes/status_{date_str}")
        lojas_enviaram_anterior = set()
        if doc_status:
            flds = doc_status.get("fields", {})
            lojas_enviaram_anterior = {l for l in ALL_LOJAS if flds.get(l, {}).get("booleanValue") is True}
    except Exception:
        lojas_enviaram_anterior = set()

    lojas_enviaram_total = lojas_enviaram_anterior | set(lojas_processadas.keys())

    # Salvar status de notificações
    try:
        salvar_status_notificacoes(date_str, lojas_enviaram_total, cocoa_shopping)
    except Exception as e:
        log(f"WARN: Não salvou notificações — {e}")

    # Atualizar estado
    state["processed_ids"] = list(processed_ids | set(novos_ids))
    state["last_run"] = ts_str
    save_state(state)

    # Notificação macOS
    faltando = [l for l in ALL_LOJAS if l not in lojas_enviaram_total]
    n_ok  = len(lojas_enviaram_total)
    n_all = len(ALL_LOJAS)
    processadas_agora = len(lojas_processadas)

    if processadas_agora > 0:
        titulo  = f"Titãs Diagnóstico — {date_str}"
        if faltando:
            msg = f"{n_ok}/{n_all} lojas enviaram. Faltam: {', '.join(faltando)}"
        else:
            msg = f"Todas as {n_all} lojas enviaram folhas! ✓"
        notificar_mac(titulo, msg)
        log(f"Processadas: {processadas_agora} novas. Erros: {erros}. {msg}")
    else:
        log(f"Nenhuma folha nova identificada (imagens: {len(imagens)}, erros: {erros})")

    log("Auto-diagnóstico concluído")
    return 0


if __name__ == "__main__":
    sys.exit(main())
