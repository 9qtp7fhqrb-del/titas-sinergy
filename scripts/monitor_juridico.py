#!/usr/bin/env python3
"""
Agente cloud — monitor de prazos jurídicos.
Lê a planilha Google Sheets com os processos, detecta audiências próximas
e documentos pendentes, e atualiza alertas no Firestore (ts_jur_rede).
Roda via GitHub Actions a cada 6h, sem depender do Mac.
"""
import csv, io, json, time, requests
from datetime import datetime, date

FIREBASE_KEY  = "AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8"
FIRESTORE_URL = "https://firestore.googleapis.com/v1/projects/titas-sinergy/databases/(default)/documents"
SHEET_URL     = "https://docs.google.com/spreadsheets/d/1SCI9hYuhq2riIA5Ms90RFx64TPtlWMeA/export?format=csv"

LOJAS_MAP = {
    "cariacica": "Cariacica", "itabuna": "Itabuna", "moxuara": "Moxuara",
    "praiadacosta": "Praia da Costa", "barreiras": "Barreiras",
    "teixeiradefre": "Teixeira de Freitas", "laranjeiras": "Laranjeiras",
    "saomateus": "São Mateus", "sao mateus": "São Mateus",
    "serra": "Serra", "montserrat": "Montserrat", "linhares": "Linhares",
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def dias_ate(d: date) -> int:
    return (d - date.today()).days

def urgencia_label(dias: int) -> tuple:
    if dias < 0:
        return f"VENCIDA há {abs(dias)}d", "critica"
    if dias == 0:
        return "HOJE", "critica"
    if dias <= 7:
        return f"{dias}d (semana)", "critica"
    if dias <= 15:
        return f"{dias}d", "alta"
    return f"{dias}d", "media"

def read_sheet():
    r = requests.get(SHEET_URL, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    reader = csv.reader(io.StringIO(r.text))
    rows = list(reader)
    # Planilha tem 2 linhas iniciais (vazia + título) antes do cabeçalho
    header_idx = next((i for i, row in enumerate(rows) if row and row[0].strip() and row[0].strip().upper() in ("LOJA", "STORE")), 2)
    headers = rows[header_idx]
    data = []
    for row in rows[header_idx + 1:]:
        if not row or not any(c.strip() for c in row):
            continue
        data.append(dict(zip(headers, row)))
    return data

def col(row, *names):
    """Busca valor em múltiplos nomes de coluna."""
    for n in names:
        for k, v in row.items():
            if k.strip().upper() == n.upper() and v.strip():
                return v.strip()
    return ""

def loja_key(nome: str) -> str:
    n = nome.lower().replace(" ", "")
    n = n.replace("ã","a").replace("ó","o").replace("á","a").replace("é","e")
    for k in LOJAS_MAP:
        if k.replace(" ","") in n:
            return k
    return n

def firestore_list():
    url = f"{FIRESTORE_URL}/ts_jur_rede?key={FIREBASE_KEY}&pageSize=200"
    r = requests.get(url, timeout=10)
    items = {}
    for doc in r.json().get("documents", []):
        doc_id = doc["name"].split("/")[-1]
        fields = doc.get("fields", {})
        item = {"id": doc_id}
        for k, v in fields.items():
            if "stringValue" in v:
                item[k] = v["stringValue"]
            elif "integerValue" in v:
                item[k] = int(v["integerValue"])
        items[doc_id] = item
    return items

def firestore_set(doc_id, data):
    fields = {}
    for k, v in data.items():
        if isinstance(v, int):
            fields[k] = {"integerValue": str(v)}
        else:
            fields[k] = {"stringValue": str(v) if v is not None else ""}
    url = f"{FIRESTORE_URL}/ts_jur_rede/{doc_id}?key={FIREBASE_KEY}"
    r = requests.patch(url, json={"fields": fields}, timeout=10)
    return r.status_code == 200

def firestore_delete(doc_id):
    url = f"{FIRESTORE_URL}/ts_jur_rede/{doc_id}?key={FIREBASE_KEY}"
    r = requests.delete(url, timeout=10)
    return r.status_code in (200, 204)

def main():
    log("=== monitor_juridico iniciado ===")

    log("Baixando planilha...")
    try:
        rows = read_sheet()
    except Exception as e:
        log(f"ERRO ao ler planilha: {e}")
        raise

    log(f"{len(rows)} processos encontrados.")
    existing = firestore_list()
    now_ms  = int(time.time() * 1000)
    today   = date.today()

    alert_ids_gerados = set()
    upserted = deleted = 0

    for row in rows:
        loja_n  = col(row, "LOJA")
        numero  = col(row, "Nº PROCESSO", "N° PROCESSO", "NUMERO", "PROCESSO")
        status  = col(row, "STATUS")
        dt_aud  = col(row, "DT. AUDIÊNCIA", "DT. AUDIENCIA", "DATA AUDIENCIA", "DT AUDIÊNCIA")
        doc_jur = col(row, "DOC. JURÍDICO", "DOC. JURIDICO")
        recl    = col(row, "RECLAMANTE")
        obs     = col(row, "OBSERVAÇÕES", "OBSERVACOES", "OBS")
        tipo    = col(row, "TIPO")

        if not numero:
            continue

        # Ignora encerrados
        if any(w in status.lower() for w in ["encerrado", "arquivado", "extinto", "baixado"]):
            continue

        lk        = loja_key(loja_n)
        loja_nome = LOJAS_MAP.get(lk, loja_n)
        num_safe  = numero.replace("/","_").replace(".","_").replace(" ","_").replace(",","_")

        # ── Alerta 1: audiência nos próximos 30 dias ────────────
        d_aud = parse_date(dt_aud)
        if d_aud:
            dias = dias_ate(d_aud)
            if dias <= 30:
                urg_label, urg_nivel = urgencia_label(dias)
                doc_id = f"deadline_alert_{lk}_{num_safe}"
                alert_ids_gerados.add(doc_id)

                status_fs = "pendente" if dias <= 7 else "aguardando_retorno"
                titulo    = f"Audiência {urg_label} — {loja_nome}"
                descricao = f"Processo {numero} ({tipo or 'PROCON'})."
                if recl:
                    descricao += f" Reclamante: {recl}."
                if obs:
                    descricao += f" {obs[:300]}"

                data = {
                    "titulo":       titulo,
                    "descricao":    descricao.strip(),
                    "tipo":         "procon" if "procon" in status.lower() or "sem audiencia" in status.lower() else "judicial",
                    "responsavel":  "Escritório Jurídico",
                    "prazo":        dt_aud,
                    "grupo":        "Monitor Automático",
                    "fonte":        "cloud_monitor",
                    "status":       status_fs,
                    "urgencia":     urg_nivel,
                    "loja":         loja_nome,
                    "processo":     numero,
                    "atualizadoEm": now_ms,
                }

                if doc_id not in existing:
                    data["criadoEm"] = now_ms

                firestore_set(doc_id, data)
                log(f"  {'↻' if doc_id in existing else '+'} Audiência {urg_label} — {loja_nome} | {numero}")
                upserted += 1

        # ── Alerta 2: documento jurídico pendente ───────────────
        if doc_jur.lower() == "pendente":
            doc_id = f"doc_pendente_{lk}_{num_safe}"
            alert_ids_gerados.add(doc_id)

            titulo    = f"Documentação pendente — {loja_nome}"
            descricao = f"Processo {numero}: documentação jurídica ainda não enviada."
            if obs:
                descricao += f" {obs[:200]}"

            data = {
                "titulo":       titulo,
                "descricao":    descricao.strip(),
                "tipo":         "documentacao",
                "responsavel":  "Escritório Jurídico",
                "prazo":        dt_aud or "",
                "grupo":        "Monitor Automático",
                "fonte":        "cloud_monitor",
                "status":       "pendente",
                "urgencia":     "alta",
                "loja":         loja_nome,
                "processo":     numero,
                "atualizadoEm": now_ms,
            }

            if doc_id not in existing:
                data["criadoEm"] = now_ms

            firestore_set(doc_id, data)
            log(f"  {'↻' if doc_id in existing else '+'} Doc pendente — {loja_nome} | {numero}")
            upserted += 1

    # Remove alertas superados (audiência > 7 dias atrás ou doc aprovado)
    for doc_id in list(existing.keys()):
        if not doc_id.startswith(("deadline_alert_", "doc_pendente_")):
            continue
        if doc_id in alert_ids_gerados:
            continue
        item = existing[doc_id]
        prazo_str = item.get("prazo", "")
        d = parse_date(prazo_str)
        if d and (today - d).days <= 7:
            continue
        firestore_delete(doc_id)
        log(f"  - Removido: {doc_id}")
        deleted += 1

    log(f"=== Concluído: {upserted} alertas | {deleted} removidos ===")

if __name__ == "__main__":
    main()
