#!/usr/bin/env python3
"""
Lê o grupo WhatsApp "Jurídico Rav Holding" via screenshot + Claude API Vision
e atualiza pendências corporativas no Firestore (ts_jur_rede).
Roda a cada 30 min via launchd quando o Mac está ligado.
"""
import os, sys, json, base64, subprocess, time, requests
from datetime import datetime

FIREBASE_KEY = "AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8"
FIRESTORE_URL = "https://firestore.googleapis.com/v1/projects/titas-sinergy/databases/(default)/documents"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOT_PATH = "/tmp/jur_wa_sync.png"
LOG_FILE = os.path.join(PROJECT_DIR, ".jur-sync.log")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)

def get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        env_file = os.path.join(PROJECT_DIR, ".env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return key

def navigate_whatsapp():
    """Ativa WhatsApp e abre o grupo Jurídico Rav Holding via busca."""
    script = """
tell application "WhatsApp" to activate
delay 2
tell application "System Events"
    tell process "WhatsApp"
        keystroke "f" using command down
        delay 0.8
        keystroke "Jurídico Rav Holding"
        delay 1.5
        key code 36
        delay 2
    end tell
end tell
"""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        log(f"AppleScript aviso: {r.stderr.strip()}")

def take_screenshot():
    subprocess.run(["screencapture", "-x", SCREENSHOT_PATH], check=True)
    with open(SCREENSHOT_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()

def extract_from_screenshot(img_b64, api_key):
    try:
        import anthropic
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
        import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": img_b64}
                },
                {
                    "type": "text",
                    "text": (
                        'Esta é uma captura de tela do Mac com o WhatsApp aberto no grupo "Jurídico Rav Holding".\n'
                        'Analise as mensagens visíveis e extraia pendências, tarefas ou assuntos jurídicos que precisam de acompanhamento.\n\n'
                        'Para cada item retorne:\n'
                        '- titulo: título curto (max 60 chars)\n'
                        '- descricao: resumo com contexto completo\n'
                        '- tipo: trabalhista | judicial | procon | documentacao | compliance | financeiro\n'
                        '- responsavel: advogado, empresa ou pessoa responsável mencionada\n'
                        '- prazo: data ou texto do prazo se houver\n'
                        '- status: pendente | aguardando_retorno | em_andamento\n\n'
                        'Ignore conversas informais. Se não há pendências claras, retorne {"itens": []}.\n'
                        'Responda SOMENTE com JSON: {"itens": [...]}'
                    )
                }
            ]
        }]
    )
    text = resp.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)

def firestore_list():
    url = f"{FIRESTORE_URL}/ts_jur_rede?key={FIREBASE_KEY}&pageSize=100"
    r = requests.get(url, timeout=10)
    items = []
    for doc in r.json().get("documents", []):
        fields = doc.get("fields", {})
        doc_id = doc["name"].split("/")[-1]
        item = {"id": doc_id}
        for k, v in fields.items():
            if "stringValue" in v:
                item[k] = v["stringValue"]
            elif "integerValue" in v:
                item[k] = int(v["integerValue"])
        items.append(item)
    return items

def firestore_create(data):
    fields = {k: {"stringValue": str(v)} if not isinstance(v, int) else {"integerValue": str(v)}
              for k, v in data.items()}
    url = f"{FIRESTORE_URL}/ts_jur_rede?key={FIREBASE_KEY}"
    r = requests.post(url, json={"fields": fields}, timeout=10)
    return r.status_code in (200, 201)

def firestore_update(doc_id, data):
    fields = {k: {"stringValue": str(v)} if not isinstance(v, int) else {"integerValue": str(v)}
              for k, v in data.items()}
    url = f"{FIRESTORE_URL}/ts_jur_rede/{doc_id}?key={FIREBASE_KEY}"
    r = requests.patch(url, json={"fields": fields}, timeout=10)
    return r.status_code == 200

def main():
    log("=== jur_whatsapp_sync iniciado ===")

    api_key = get_api_key()
    if not api_key:
        log("ERRO: ANTHROPIC_API_KEY não encontrada. Adicione ao .env do projeto.")
        sys.exit(1)

    log("Navegando para o grupo WhatsApp...")
    try:
        navigate_whatsapp()
    except Exception as e:
        log(f"ERRO na navegação: {e}")
        sys.exit(1)

    log("Capturando tela...")
    try:
        img = take_screenshot()
    except Exception as e:
        log(f"ERRO no screenshot: {e}")
        sys.exit(1)

    log("Analisando mensagens com Claude Haiku...")
    try:
        result = extract_from_screenshot(img, api_key)
    except json.JSONDecodeError as e:
        log(f"ERRO: resposta inválida do Claude: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"ERRO na análise: {e}")
        sys.exit(1)

    itens = result.get("itens", [])
    log(f"Itens detectados: {len(itens)}")
    if not itens:
        log("Nenhuma pendência nova. Encerrando.")
        return

    existing = firestore_list()
    ex_map = {e.get("titulo", "").lower(): e for e in existing}

    now_ms = int(time.time() * 1000)
    added = updated = skipped = 0

    for item in itens:
        key = item.get("titulo", "").lower()
        base = {
            "titulo":       item.get("titulo", ""),
            "descricao":    item.get("descricao", ""),
            "tipo":         item.get("tipo", "judicial"),
            "responsavel":  item.get("responsavel", ""),
            "prazo":        item.get("prazo", ""),
            "grupo":        "Jurídico Rav Holding",
            "fonte":        "whatsapp_auto",
            "atualizadoEm": now_ms,
        }

        if key in ex_map:
            ex = ex_map[key]
            novo_status = item.get("status", "pendente")
            if ex.get("status") != novo_status:
                firestore_update(ex["id"], {**base, "status": novo_status})
                log(f"  ↻ {item['titulo']} → {novo_status}")
                updated += 1
            else:
                log(f"  = {item['titulo']} (sem mudança)")
                skipped += 1
        else:
            firestore_create({**base, "status": item.get("status", "pendente"), "criadoEm": now_ms})
            log(f"  + {item['titulo']}")
            added += 1

    log(f"=== Concluído: +{added} novos | ↻{updated} atualizados | ={skipped} sem mudança ===")

if __name__ == "__main__":
    main()
