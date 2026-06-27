"""
Usage:
  python gemma_simple.py tt35027300
  python gemma_simple.py tt35027300 --lang Hindi --quality 1080
"""

import re, sys, os, json, base64, requests, argparse, random
from urllib.parse import quote

PROXIES = [
    ("31.59.20.176",    6754),
    ("31.56.127.193",   7684),
    ("45.38.107.97",    6014),
    ("38.154.203.95",   5863),
    ("198.105.121.200", 6462),
    ("64.137.96.74",    6641),
    ("198.23.243.226",  6361),
    ("38.154.185.97",   6370),
    ("142.111.67.146",  5611),
    ("191.96.254.138",  6185),
]
PROXY_USER = "ygxmhkcc"
PROXY_PASS = "n3batopqanpg"

BASE = "https://gemma416okl.com"
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def make_session(host, port):
    proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{host}:{port}"
    s = requests.Session()
    s.proxies = {"http": proxy_url, "https": proxy_url}
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    return s


def get_working_session(imdb_id):
    proxy_list = PROXIES.copy()
    random.shuffle(proxy_list)
    for host, port in proxy_list:
        print(f"[*] Trying proxy {host}:{port} ...", flush=True)
        try:
            s = make_session(host, port)
            r = s.get(f"{BASE}/play/{imdb_id}", timeout=15)
            print(f"    HTTP {r.status_code}", flush=True)
            if r.status_code == 200:
                print(f"[+] Connected via {host}:{port}", flush=True)
                return s, r.text
        except Exception as e:
            print(f"    failed: {e}", flush=True)
    return None, None


def post(s, url, token, referer):
    r = s.post(url, data="", headers={
        "X-CSRF-Token": token,
        "Origin": BASE,
        "Referer": referer,
        "Content-Type": "application/x-www-form-urlencoded",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }, timeout=15)
    r.raise_for_status()
    raw = r.content
    try:
        d = base64.b64decode(raw).decode()
        if d.startswith(("[", "{", "#", "http")):
            return d
    except Exception:
        pass
    return raw.decode()


def variants(m3u8, base_url):
    lines = m3u8.strip().splitlines()
    out = []
    for i, line in enumerate(lines):
        if "#EXT-X-STREAM-INF" in line and i + 1 < len(lines):
            res = re.search(r'RESOLUTION=(\S+)', line)
            bw  = re.search(r'BANDWIDTH=(\d+)', line)
            res = res.group(1) if res else "?"
            bw  = int(bw.group(1)) if bw else 0
            path = lines[i+1].strip().lstrip("./")
            url  = path if path.startswith("http") else base_url.rsplit("/",1)[0] + "/" + path
            out.append((bw, res, url))
    return sorted(out, reverse=True)


def extract(imdb_id, lang_filter="", quality_filter="ALL"):
    S, html = get_working_session(imdb_id)
    if not html:
        print("[-] All proxies failed.")
        sys.exit(1)

    referer = f"{BASE}/play/{imdb_id}"

    m = re.search(r'let\s+p3\s*=\s*(\{.+?\});', html, re.DOTALL)
    if not m:
        print("[-] Player config not found.")
        print(f"[debug] Page snippet:\n{html[:500]}")
        sys.exit(1)

    cfg = json.loads(m.group(1))
    token, file_path = cfg["key"], cfg["file"]
    print(f"[+] Token : {token[:30]}...")
    print(f"[+] File  : {file_path[:60]}...")

    tracks = json.loads(post(S, file_path, token, referer))
    print(f"[+] {len(tracks)} track(s): {[t.get('title') for t in tracks]}")

    results = []
    for t in tracks:
        if not t.get("file"):
            continue
        lang = t.get("title", "?")
        if lang_filter and lang_filter.lower() not in lang.lower():
            continue

        fp     = t["file"]
        pl     = (fp[1:] + ".txt") if fp.startswith("~") else (fp if fp.startswith("http") else fp + ".txt")
        pl_url = f"{BASE}/playlist/{quote(pl, safe='')}" if not pl.startswith("http") else pl

        print(f"\n[*] Track '{lang}'", flush=True)
        try:
            raw = post(S, pl_url, token, referer).strip()
        except Exception as e:
            print(f"  [-] POST failed: {e}")
            continue

        all_vars = []
        if "#EXTM3U" in raw:
            all_vars = variants(raw, pl_url)
        elif raw.startswith("http"):
            m3u8_url = raw.splitlines()[0]
            try:
                master = S.get(m3u8_url, headers={"Referer": BASE+"/", "Origin": BASE}, timeout=15).text
                all_vars = variants(master, m3u8_url)
            except Exception as e:
                print(f"  [-] Master fetch failed: {e}")
        else:
            print(f"  [-] Unexpected: {raw[:100]}")

        for bw, res, stream_url in all_vars:
            if quality_filter != "ALL" and f"/{quality_filter}/" not in stream_url:
                continue
            results.append((lang, res, bw, stream_url))
            print(f"  [+] {lang:<10} {res:<12} {bw//1000:>4}k")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("imdb_id")
    parser.add_argument("--lang",    default="",    help="Filter by language e.g. Hindi")
    parser.add_argument("--quality", default="ALL", help="1080 / 720 / 480 / 360 / ALL")
    args = parser.parse_args()

    imdb_id = args.imdb_id.rstrip("/").split("/")[-1]
    streams  = extract(imdb_id, args.lang, args.quality)

    if not streams:
        print("\n[-] No streams found.")
        sys.exit(1)

    print(f"\n{'─'*80}")
    print(f"{'LANG':<10} {'RES':<12} {'KBPS':>6}  URL")
    print(f"{'─'*80}")
    for lang, res, bw, url in streams:
        print(f"{lang:<10} {res:<12} {bw//1000:>5}k  {url}")

    print(f"\nBEST: {streams[0][3]}")