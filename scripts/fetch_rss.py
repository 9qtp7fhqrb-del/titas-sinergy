#!/usr/bin/env python3
"""Busca feeds RSS do G1 e salva no Firestore (ts_olha_isso)."""
import os, sys, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

FIREBASE_KEY  = 'AIzaSyDFrLshzqf8Ct9U1SkM9MSveDNPuy_2--8'
FIREBASE_PROJ = 'titas-sinergy'
FS_BASE = f'https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJ}/databases/(default)/documents'

FEEDS = {
    'varejo': 'https://g1.globo.com/rss/g1/economia/',
    'global': 'https://g1.globo.com/rss/g1/mundo/',
    'bahia':  'https://g1.globo.com/rss/g1/bahia/',
    'es':     'https://g1.globo.com/rss/g1/espirito-santo/',
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; TitasSinergy/1.0)'}


def fetch_feed(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {'media': 'http://search.yahoo.com/mrss/'}
    items = []
    for item in root.findall('.//item'):
        title = (item.findtext('title') or '').strip()
        link  = (item.findtext('link') or '').strip()
        pub   = (item.findtext('pubDate') or '').strip()
        desc_el = item.find('description')
        desc = ''
        if desc_el is not None:
            desc = (desc_el.text or '').strip()
        items.append({'title': title, 'link': link, 'pubDate': pub, 'description': desc})
    return items[:20]


def to_fs_array(items):
    def to_map(it):
        return {'mapValue': {'fields': {
            'title':       {'stringValue': it['title']},
            'link':        {'stringValue': it['link']},
            'pubDate':     {'stringValue': it['pubDate']},
            'description': {'stringValue': it['description']},
        }}}
    return {'arrayValue': {'values': [to_map(i) for i in items]}}


def save_to_firestore(feed_key, items):
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {'fields': {
        'updated': {'stringValue': now_iso},
        'items':   to_fs_array(items),
    }}
    url = (f'{FS_BASE}/ts_olha_isso/{feed_key}'
           f'?key={FIREBASE_KEY}'
           f'&updateMask.fieldPaths=updated&updateMask.fieldPaths=items')
    r = requests.patch(url, json=payload, timeout=20)
    r.raise_for_status()
    return r.status_code


def main():
    ok = 0
    for key, feed_url in FEEDS.items():
        try:
            items = fetch_feed(feed_url)
            status = save_to_firestore(key, items)
            print(f'  [{key}] {len(items)} itens → Firestore {status}')
            ok += 1
        except Exception as e:
            print(f'  [{key}] ERRO: {e}', file=sys.stderr)
        time.sleep(1)
    print(f'Feeds salvos: {ok}/{len(FEEDS)}')
    if ok == 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
