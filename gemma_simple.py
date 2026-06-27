"""
Usage:
  python gemma_simple.py tt35027300
  python gemma_simple.py tt35027300 --lang Hindi --quality 1080
  python gemma_simple.py https://gemma416okl.com/play/tt35027300
"""

import re, sys, json, base64, requests, argparse
from urllib.parse import quote

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# ── try multiple known base domains in case one is down
BASES = [
    "https://gemma416okl.com",
    "https://www.gemma416okl.com",
]


def find_base(imdb_id):
    """Try each base domain and return the first that responds."""
    for base in BASES:
        url = f"{base}/play/{imdb_id}"
        try:
            r = S.get(url, timeout=15, allow_redirects=True)
            print(f"[*] Trying {url}  →  HTTP {r.status_code}")
            if r.status_code == 200:
                return base, url, r.text
        except Exception as e:
            print(f"[!] {base} failed: {e}")
    return None, None, None


def post(url, token, referer):
    r = S.post(url, data="", headers={
        "X-CSRF-Token": token,
        "Origin": referer.split("/play/")[0],
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
    # Step 1: find working domain + load page
    base, referer, html = find_base(imdb_id)
    if not html:
        print("[-] All domains returned 404 or failed.")
        print("    The site may be down, blocked by GitHub's IP, or the domain changed.")
        sys.exit(1)

    # Step 2: parse player config
    m = re.search(r'let\s+p3\s*=\s*(\{.+?\});', html, re.DOTALL)
    if not m:
        # dump first 500 chars for debugging
        print("[-] Player config (let p3 = {...}) not found.")
        print(f"[debug] Page snippet:\n{html[:500]}")
        sys.exit(1)

    cfg = json.loads(m.group(1))
    token, file_path = cfg["key"], cfg["file"]
    print(f"[+] Token : {token[:30]}...")
    print(f"[+] File  : {file_path[:60]}...")

    # Step 3: track list
    tracks = json.loads(post(file_path, token, referer))
    print(f"[+] {len(tracks)} track(s) found: {[t.get('title') for t in tracks]}")

    # Step 4: per track → stream URLs
    results = []
    for t in tracks:
        if not t.get("file"):
            continue
        lang = t.get("title", "?")
        if lang_filter and lang_filter.lower() not in lang.lower():
            continue

        fp  = t["file"]
        pl  = (fp[1:] + ".txt") if fp.startswith("~") else (fp if fp.startswith("http") else fp + ".txt")
        pl_url = f"{base}/playlist/{quote(pl, safe='')}" if not pl.startswith("http") else pl

        print(f"\n[*] Track '{lang}' → {pl_url[:60]}...")
        try:
            raw = post(pl_url, token, referer).strip()
        except Exception as e:
            print(f"  [-] POST failed: {e}")
            continue

        all_vars = []
        if "#EXTM3U" in raw:
            all_vars = variants(raw, pl_url)
        elif raw.startswith("http"):
            m3u8_url = raw.splitlines()[0]
            print(f"  [*] Fetching master: {m3u8_url[:60]}...")
            try:
                master = S.get(m3u8_url, headers={"Referer": base+"/", "Origin": base}, timeout=15).text
                all_vars = variants(master, m3u8_url)
            except Exception as e:
                print(f"  [-] Master fetch failed: {e}")
        else:
            print(f"  [-] Unexpected response: {raw[:100]}")

        for bw, res, stream_url in all_vars:
            if quality_filter != "ALL" and f"/{quality_filter}/" not in stream_url:
                continue
            results.append((lang, res, bw, stream_url))
            print(f"  [+] {lang:<10} {res:<12} {bw//1000:>4}k  {stream_url}")

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