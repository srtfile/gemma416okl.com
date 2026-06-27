"""
Usage:
  python gemma_simple.py tt35027300
  python gemma_simple.py tt35027300 --lang Hindi --quality 1080
"""

import re, sys, json, base64, requests, argparse
from urllib.parse import quote

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
BASE = "https://gemma416okl.com"


def get(url):
    r = S.get(url, timeout=15)
    r.raise_for_status()
    return r.text


def post(url, token, referer):
    r = S.post(url, data="", headers={
        "X-CSRF-Token": token,
        "Origin": BASE,
        "Referer": referer,
        "Content-Type": "application/x-www-form-urlencoded",
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


def variants(m3u8, base):
    lines = m3u8.strip().splitlines()
    out = []
    for i, line in enumerate(lines):
        if "#EXT-X-STREAM-INF" in line and i + 1 < len(lines):
            res = re.search(r'RESOLUTION=(\S+)', line)
            bw  = re.search(r'BANDWIDTH=(\d+)', line)
            res = res.group(1) if res else "?"
            bw  = int(bw.group(1)) if bw else 0
            path = lines[i+1].strip().lstrip("./")
            url  = path if path.startswith("http") else base.rsplit("/",1)[0] + "/" + path
            out.append((bw, res, url))
    return sorted(out, reverse=True)


def extract(imdb_id, lang_filter="", quality_filter="ALL"):
    referer = f"{BASE}/play/{imdb_id}"

    # Step 1: token + file
    html = get(referer)
    m = re.search(r'let\s+p3\s*=\s*(\{.+?\});', html, re.DOTALL)
    if not m:
        print("[-] Player config not found in page.")
        sys.exit(1)
    cfg = json.loads(m.group(1))
    token, file_path = cfg["key"], cfg["file"]

    # Step 2: track list
    tracks = json.loads(post(file_path, token, referer))

    # Step 3: per track → stream URLs
    results = []
    for t in tracks:
        if not t.get("file"):
            continue

        lang = t.get("title", "?")

        # apply language filter
        if lang_filter and lang_filter.lower() not in lang.lower():
            continue

        fp  = t["file"]
        pl  = (fp[1:] + ".txt") if fp.startswith("~") else (fp if fp.startswith("http") else fp + ".txt")
        url = f"{BASE}/playlist/{quote(pl, safe='')}" if not pl.startswith("http") else pl

        try:
            raw = post(url, token, referer).strip()
        except Exception as e:
            print(f"  [-] {lang}: {e}")
            continue

        all_vars = []
        if "#EXTM3U" in raw:
            all_vars = variants(raw, pl)
        elif raw.startswith("http"):
            try:
                master = S.get(raw.splitlines()[0], headers={"Referer": BASE+"/", "Origin": BASE}, timeout=15).text
                all_vars = variants(master, raw.splitlines()[0])
            except Exception as e:
                print(f"  [-] {lang} master fetch: {e}")

        for bw, res, stream_url in all_vars:
            # apply quality filter
            if quality_filter != "ALL" and f"/{quality_filter}/" not in stream_url:
                continue
            results.append((lang, res, bw, stream_url))

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("imdb_id")
    parser.add_argument("--lang",    default="",    help="Filter by language (e.g. Hindi)")
    parser.add_argument("--quality", default="ALL", help="Quality: 1080 / 720 / 480 / 360 / ALL")
    args = parser.parse_args()

    imdb_id = args.imdb_id.rstrip("/").split("/")[-1]
    streams  = extract(imdb_id, args.lang, args.quality)

    if not streams:
        print("[-] No streams found.")
        sys.exit(1)

    print(f"\n{'─'*80}")
    print(f"{'LANG':<10} {'RES':<12} {'KBPS':>6}  URL")
    print(f"{'─'*80}")
    for lang, res, bw, url in streams:
        print(f"{lang:<10} {res:<12} {bw//1000:>5}k  {url}")

    print(f"\nBEST: {streams[0][3]}")