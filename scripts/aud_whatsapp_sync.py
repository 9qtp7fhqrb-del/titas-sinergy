#!/usr/bin/env python3
"""
Audiências WhatsApp Sync — extração por regex (sem API Anthropic).
Lê "Demandas Jurídicas" e "PENDENCIAS JURIDICAS REDE TITÃS" via SQLite
e preenche ts_audiencias no Firestore.
Roda ao ligar o Mac + a cada hora via LaunchAgent com.titas.aud-sync.
"""
import os, re, json, sqlite3, datetime, hashlib, urllib.request
from pathlib import Path

# ════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════
WA_DB = Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
GRUPOS = {803: "Demandas Jurídicas", 28: "PENDENCIAS JURIDICAS"}

FIREBASE_KEY  = "AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8"
FIRESTORE_URL = "https://firestore.googleapis.com/v1/projects/titas-sinergy/databases/(default)/documents"
STATE_FILE    = Path.home() / ".titas_aud_state.json"
PROJECT_DIR   = Path(__file__).parent.parent
LOG_FILE      = PROJECT_DIR / ".aud-sync.log"
HISTORICO_DIAS = 120

LOJA_MAP = {
    "cariacica": "cariacica", "itabuna": "itabuna",
    "moxuara": "moxuara", "shopping moxuara": "moxuara",
    "praia da costa": "praiadacosta", "praiadacosta": "praiadacosta",
    "barreiras": "barreiras",
    "teixeira": "teixeira", "teixeira de freitas": "teixeira",
    "laranjeiras": "laranjeiras",
    "são mateus": "saomateus", "sao mateus": "saomateus",
    "saomateus": "saomateus", "sm telefonia": "saomateus",
    "itbn": "itabuna",
    "serra": "serra", "montserrat": "montserrat", "linhares": "linhares",
    "mox telefonia": "moxuara", "vr dias": "cariacica",
    "mp aguiar": "praiadacosta", "r&v": "",
}


# ════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════
def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ════════════════════════════════════════════════
# ESTADO
# ════════════════════════════════════════════════
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f)
    except Exception as e:
        log(f"WARN estado: {e}")


# ════════════════════════════════════════════════
# WHATSAPP
# ════════════════════════════════════════════════
def cocoa_desde_date(d):
    epoch = datetime.datetime(2001, 1, 1)
    return (datetime.datetime(d.year, d.month, d.day) - epoch).total_seconds()

def buscar_msgs(grupo_id, cocoa_desde):
    if not WA_DB.exists():
        log("ERRO: WhatsApp DB não encontrado")
        return []
    conn = sqlite3.connect(str(WA_DB))
    cur  = conn.cursor()
    cur.execute("""
        SELECT m.Z_PK, m.ZMESSAGEDATE, m.ZTEXT
        FROM ZWAMESSAGE m
        WHERE m.ZCHATSESSION = ?
          AND m.ZTEXT IS NOT NULL AND m.ZTEXT != ''
          AND m.ZMESSAGEDATE >= ?
        ORDER BY m.ZMESSAGEDATE
    """, (grupo_id, cocoa_desde))
    rows = cur.fetchall()
    conn.close()
    epoch = datetime.datetime(2001, 1, 1)
    result = []
    for pk, cocoa, texto in rows:
        dt = epoch + datetime.timedelta(seconds=cocoa)
        result.append({"pk": pk, "cocoa": cocoa, "texto": texto,
                       "data_msg": dt.strftime("%Y-%m-%d")})
    return result


# ════════════════════════════════════════════════
# EXTRAÇÃO POR REGEX
# ════════════════════════════════════════════════
def parse_data_br(s):
    """DD/MM/YYYY ou DD/MM → YYYY-MM-DD. Retorna None se inválido."""
    m = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{4}))?', s)
    if not m:
        return None
    d, mo, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    if not ano:
        # Infere o ano: usa o próximo ocorrência futura
        hoje = datetime.date.today()
        ano = hoje.year
        candidate = datetime.date(ano, mo, d) if 1 <= mo <= 12 and 1 <= d <= 31 else None
        if candidate and candidate < hoje - datetime.timedelta(days=30):
            ano += 1
    else:
        ano = int(ano)
    try:
        datetime.date(ano, mo, d)
        return f"{ano:04d}-{mo:02d}-{d:02d}"
    except ValueError:
        return None

def parse_horario(s):
    m = re.search(r'(\d{1,2})[h:h](\d{2})?', s, re.IGNORECASE)
    if not m:
        return ""
    h = int(m.group(1))
    mi = int(m.group(2)) if m.group(2) else 0
    return f"{h:02d}:{mi:02d}"

def parse_tipo(s):
    sl = s.lower()
    if "híbrida" in sl or "hibrida" in sl or "presencial/virtual" in sl or \
       "virtual/presencial" in sl or "telepresencial" in sl:
        return "hibrida"
    if "virtual" in sl or "online" in sl or "zoom" in sl or "meet" in sl or \
       "lifesize" in sl or "teams" in sl:
        return "online"
    if "presencial" in sl:
        return "presencial"
    return "presencial"

def detectar_loja(texto):
    tl = texto.lower()
    for alias, key in LOJA_MAP.items():
        if alias in tl:
            return key
    return ""

def extrair_audiencias_regex(msgs):
    """
    Processa mensagens individualmente + janela de contexto (3 msgs anteriores)
    para capturar processo/partes que vêm em mensagem separada.
    """
    # Regex de campos estruturados (cada campo em linha própria)
    re_data    = re.compile(r'\*?Data\*?\s*:\s*\*?\s*([\d/]+)', re.IGNORECASE)
    re_horario = re.compile(r'\*?Hor[aá]rio\*?\s*:\s*\*?\s*([0-9h:Hh ]+(?:hrs?)?)', re.IGNORECASE)
    re_formato = re.compile(r'\*?Formato\*?\s*:\s*\*?\s*([^\n*]+)', re.IGNORECASE)
    re_local   = re.compile(r'\*?(?:Local[^:]*|Link[^:]*)\*?\s*:\s*\*?\s*([^\n*]+)', re.IGNORECASE)
    re_proc    = re.compile(
        r'processo\s+\*?([0-9.\-]+)\*?[^*\n]*partes\s+s[aã]o\s+\*?([^*\n]+?)\*?\s+e\s+\*?([^*\n]+?)\*?[\.\s]',
        re.IGNORECASE | re.DOTALL)
    re_proc2   = re.compile(r'processo\s+(?:nº|n\.)?\s*\*?([0-9.\-]+)\*?', re.IGNORECASE)
    re_partes  = re.compile(r'partes\s+s[aã]o\s+\*?(.+?)\*?\s+e\s+\*?(.+?)\*?[\.\n]', re.IGNORECASE | re.DOTALL)
    re_recl    = re.compile(r'Reclamante\*?\s*:\s*\*?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÀÜ][A-ZÁÉÍÓÚÂÊÔÃÕÀÜa-záéíóúâêôãõàü\s]+)', re.IGNORECASE)

    resultados = []

    for i, m in enumerate(msgs):
        texto = m["texto"]

        # Só processa msgs com o bloco estruturado
        dm = re_data.search(texto)
        if not dm:
            continue

        data_str = parse_data_br(dm.group(1))
        if not data_str:
            continue

        # Ignora passadas há mais de 30 dias
        try:
            d_aud = datetime.date.fromisoformat(data_str)
            if d_aud < datetime.date.today() - datetime.timedelta(days=30):
                continue
        except ValueError:
            continue

        hm = re_horario.search(texto)
        fm = re_formato.search(texto)
        lm = re_local.search(texto)

        horario = parse_horario(hm.group(1)) if hm else ""
        tipo    = parse_tipo(fm.group(1))    if fm else "presencial"
        local   = lm.group(1).strip().rstrip("*").strip() if lm else ""

        # Contexto = mensagem atual + até 4 anteriores (para pegar processo/partes)
        contexto = " ".join(msgs[max(0, i-4):i+1][j]["texto"] for j in range(min(5, i+1)))

        pm = re_proc.search(contexto)
        if pm:
            num = pm.group(1).strip()
            pa  = pm.group(2).strip().rstrip("*,.")
            pb  = pm.group(3).strip().rstrip("*,.")
            proc = f"{num} — {pa} vs {pb}"
        else:
            # Tenta pegar número separado das partes
            nm = re_proc2.search(contexto)
            pm2 = re_partes.search(contexto)
            rm = re_recl.search(texto)
            if nm and pm2:
                proc = f"{nm.group(1).strip()} — {pm2.group(1).strip()} vs {pm2.group(2).strip()}"
            elif nm:
                proc = nm.group(1).strip()
            elif rm:
                proc = rm.group(1).strip()
            else:
                # Último recurso: qualquer nº de processo no contexto
                any_proc = re.search(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}', contexto)
                proc = any_proc.group(0) if any_proc else "Audiência Jurídica"

        loja = detectar_loja(contexto)

        resultados.append({
            "processo": proc[:120],
            "data":     data_str,
            "horario":  horario,
            "tipo":     tipo,
            "local":    local[:200],
            "loja":     loja,
            "obs":      "",
        })

    # Deduplicar por (data, horario, proc[:40])
    seen = set()
    dedup = []
    for r in resultados:
        key = (r["data"], r["horario"], r["processo"][:40].lower())
        if key not in seen:
            seen.add(key)
            dedup.append(r)

    return dedup


# ════════════════════════════════════════════════
# FIRESTORE
# ════════════════════════════════════════════════
def fs_list():
    url = f"{FIRESTORE_URL}/ts_audiencias?key={FIREBASE_KEY}&pageSize=500"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        log(f"WARN Firestore list: {e}")
        return {}
    result = {}
    for doc in data.get("documents", []):
        doc_id = doc["name"].split("/")[-1]
        f = doc.get("fields", {})
        result[doc_id] = {k: v.get("stringValue", "") for k, v in f.items()}
    return result

def fs_patch(doc_id, fields_dict):
    url  = f"{FIRESTORE_URL}/ts_audiencias/{doc_id}?key={FIREBASE_KEY}"
    body = json.dumps({"fields": {k: {"stringValue": str(v)} for k, v in fields_dict.items()}}).encode()
    req  = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()

def gerar_id(proc, data):
    h = hashlib.md5(f"{data}_{proc[:60].lower()}".encode()).hexdigest()[:8]
    return f"aud_{data.replace('-','')}_{h}"


# ════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════
def main():
    log("=" * 55)
    log("aud_whatsapp_sync iniciado (modo regex — sem API)")

    if not WA_DB.exists():
        log("ERRO: WhatsApp Desktop não instalado ou BD não encontrado.")
        return 1

    state = load_state()

    log("Carregando audiências existentes do Firestore...")
    try:
        existentes = fs_list()
    except Exception as e:
        log(f"WARN: {e}")
        existentes = {}
    log(f"  {len(existentes)} audiências já cadastradas")

    total_novas = total_atualizadas = 0

    for grupo_id, grupo_nome in GRUPOS.items():
        log(f"\nGrupo: {grupo_nome} (ID {grupo_id})")

        key_state = f"ultimo_cocoa_{grupo_id}"
        if state.get(key_state):
            cocoa_desde = float(state[key_state]) + 1
        else:
            d_inicio = datetime.date.today() - datetime.timedelta(days=HISTORICO_DIAS)
            cocoa_desde = cocoa_desde_date(d_inicio)
            log(f"  Primeira execução — buscando {HISTORICO_DIAS} dias de histórico")

        msgs = buscar_msgs(grupo_id, cocoa_desde)
        log(f"  {len(msgs)} mensagens encontradas")
        if not msgs:
            continue

        state[key_state] = max(m["cocoa"] for m in msgs)

        audiencias = extrair_audiencias_regex(msgs)
        log(f"  {len(audiencias)} audiência(s) extraída(s) por regex")

        for a in audiencias:
            doc_id = gerar_id(a["processo"], a["data"])
            fields = {**a,
                      "fonte":     f"whatsapp_{grupo_nome[:20]}",
                      "criadoEm": datetime.datetime.now().isoformat()}

            if doc_id in existentes:
                ex = existentes[doc_id]
                if ex.get("horario") == a["horario"] and ex.get("local") == a["local"]:
                    log(f"    = {a['data']} {a['horario']} — {a['processo'][:50]} (sem mudança)")
                    continue
                log(f"    ↻ {a['data']} {a['horario']} — {a['processo'][:50]}")
                total_atualizadas += 1
            else:
                log(f"    + {a['data']} {a['horario']} — {a['processo'][:50]}")
                total_novas += 1

            try:
                fs_patch(doc_id, fields)
                existentes[doc_id] = fields
            except Exception as e:
                log(f"    ERRO Firestore: {e}")

    save_state(state)

    if total_novas > 0 or total_atualizadas > 0:
        msg = f"{total_novas} nova(s) + {total_atualizadas} atualizada(s)"
        os.system(f'osascript -e \'display notification "{msg}" with title "📅 Audiências sincronizadas" sound name "Ping"\'')
        log(f"\nConcluído: {msg}")
    else:
        log("\nConcluído: nenhuma audiência nova.")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
