#!/usr/bin/env python3
"""Collect V2Ray configs from public Telegram channels (via t.me/s) and
write them into categorized files.

No Telegram API key needed: public channels are fetched from their web view,
the same approach as the Bale config forwarder.

Sources: channels.json (list of channel usernames, e.g. ["persianvpnhub"])
Outputs (under configs/):
  all.txt            every unique config, newest first
  all_base64.txt     base64(all.txt) — subscription for V2RayNG / v2ray clients
  vless.txt / vmess.txt / trojan.txt / shadowsocks.txt / tuic.txt / hysteria2.txt
  countries/<CODE>.txt   one file per country, e.g. DE.txt, US.txt, NL.txt
  countries/unknown.txt  configs whose post had no recognizable location
  (files are only written when they have at least one config)
Plus stats.json at the repo root with counts and the last run time.

Location is taken from the post header, e.g.:
  "📂 کانفیگ VLESS | 📍 لوکیشن: آلمان 🇩🇪 | ..."
so it works even when the config itself carries no country name.
Fallback: the flag emoji in the header, then "unknown".

Usage: python3 collect.py
"""
import base64
import html
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.path.join(BASE, "channels.json")
OUT_DIR = os.path.join(BASE, "configs")
COUNTRIES_DIR = os.path.join(OUT_DIR, "countries")
STATS_FILE = os.path.join(BASE, "stats.json")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

PROTOCOLS = ("vmess", "vless", "trojan", "ss", "ssr", "tuic", "hysteria2", "hy2")
# File name per protocol (ss -> shadowsocks, hy2 -> hysteria2)
PROTOCOL_FILES = {
    "vmess": "vmess.txt",
    "vless": "vless.txt",
    "trojan": "trojan.txt",
    "ss": "shadowsocks.txt",
    "ssr": "shadowsocksr.txt",
    "tuic": "tuic.txt",
    "hysteria2": "hysteria2.txt",
    "hy2": "hysteria2.txt",
}

# Persian and English location names -> ISO country code.
COUNTRY_NAMES = {
    # Persian
    "آلمان": "DE", "امریکا": "US", "آمریکا": "US", "فرانسه": "FR",
    "انگلیس": "GB", "بریتانیا": "GB", "هلند": "NL", "روسیه": "RU",
    "فنلاند": "FI", "لیتوانی": "LT", "استونی": "EE", "رومانی": "RO",
    "ترکیه": "TR", "کانادا": "CA", "ژاپن": "JP", "کره": "KR",
    "کره جنوبی": "KR", "سنگاپور": "SG", "امارات": "AE", "سوئد": "SE",
    "نروژ": "NO", "دانمارک": "DK", "لهستان": "PL", "ایتالیا": "IT",
    "اسپانیا": "ES", "اتریش": "AT", "سوئیس": "CH", "بلژیک": "BE",
    "ایرلند": "IE", "پرتغال": "PT", "یونان": "GR", "اوکراین": "UA",
    "هند": "IN", "برزیل": "BR", "استرالیا": "AU", "مجارستان": "HU",
    "چک": "CZ", "بلغارستان": "BG", "کرواسی": "HR", "صربستان": "RS",
    "مولداوی": "MD", "لتونی": "LV", "ایسلند": "IS", "لوکزامبورگ": "LU",
    "مالزی": "MY", "اندونزی": "ID", "ویتنام": "VN", "تایلند": "TH",
    "فیلیپین": "PH", "مکزیک": "MX", "آرژانتین": "AR", "شیلی": "CL",
    "آفریقای جنوبی": "ZA", "مصر": "EG", "نیجریه": "NG", "کنیا": "KE",
    "کلودفلر": "CLOUDFLARE", "کلادفلر": "CLOUDFLARE",
    # English
    "germany": "DE", "united states": "US", "usa": "US", "america": "US",
    "france": "FR", "england": "GB", "united kingdom": "GB", "uk": "GB",
    "netherlands": "NL", "russia": "RU", "finland": "FI", "lithuania": "LT",
    "estonia": "EE", "romania": "RO", "turkey": "TR", "canada": "CA",
    "japan": "JP", "korea": "KR", "south korea": "KR", "singapore": "SG",
    "uae": "AE", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "poland": "PL", "italy": "IT", "spain": "ES", "austria": "AT",
    "switzerland": "CH", "belgium": "BE", "ireland": "IE", "portugal": "PT",
    "greece": "GR", "ukraine": "UA", "india": "IN", "brazil": "BR",
    "australia": "AU", "hungary": "HU", "czech": "CZ", "czechia": "CZ",
    "bulgaria": "BG", "croatia": "HR", "serbia": "RS", "moldova": "MD",
    "latvia": "LV", "iceland": "IS", "luxembourg": "LU", "malaysia": "MY",
    "indonesia": "ID", "vietnam": "VN", "thailand": "TH",
    "philippines": "PH", "mexico": "MX", "argentina": "AR", "chile": "CL",
    "south africa": "ZA", "egypt": "EG", "nigeria": "NG", "kenya": "KE",
    "cloudflare": "CLOUDFLARE",
}

FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
LOCATION_RE = re.compile(r"لوکیشن:\s*([^|#\n]+)")
CONFIG_RE = re.compile(
    r"(?:vmess|vless|trojan|ss|ssr|tuic|hysteria2|hy2)://[^\s\"'<>`]+"
)


def flag_to_code(flag: str) -> str | None:
    """'🇩🇪' -> 'DE' (regional-indicator pair)."""
    if len(flag) != 2:
        return None
    try:
        return "".join(chr(ord(c) - 0x1F1E6 + ord("A")) for c in flag)
    except Exception:
        return None


def extract_location(text: str) -> str:
    m = LOCATION_RE.search(text)
    if m:
        raw = m.group(1).strip()
        # Cloudflare posts carry a ☁️ instead of a flag, e.g. "کلودفلر ☁️".
        if "کلودفلر" in raw or "کلادفلر" in raw or "cloudflare" in raw.lower():
            return "CLOUDFLARE"
        # Name part before any flag emoji.
        name = FLAG_RE.sub("", raw).strip().strip("-–—").strip()
        if name:
            code = COUNTRY_NAMES.get(name) or COUNTRY_NAMES.get(name.lower())
            if code:
                return code
        flag = FLAG_RE.search(raw)
        if flag:
            code = flag_to_code(flag.group(0))
            if code:
                return code
    # Fallback: any flag emoji anywhere in the post header.
    flag = FLAG_RE.search(text)
    if flag:
        code = flag_to_code(flag.group(0))
        if code:
            return code
    return "UNKNOWN"


def clean_config(raw: str) -> str:
    return raw.rstrip(".,)]}>").strip()


def b64_decode_padded(s: str) -> bytes:
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4))


def dedupe_key(cfg: str) -> str | None:
    """Core identity of a config (fragment/name ignored), or None if invalid."""
    proto, _, rest = cfg.partition("://")
    proto = proto.lower()
    if proto == "vmess":
        try:
            data = json.loads(b64_decode_padded(rest.split("#")[0].split("?")[0]))
            return f"vmess|{data.get('add')}|{data.get('id')}|{data.get('port')}"
        except Exception:
            return None
    core = rest.split("#")[0].split("?")[0] if proto == "ss" else rest.split("#")[0]
    # vless/trojan/tuic/hysteria2/ss: user@host:port (+query) must be present
    if "@" not in core:
        # ss:// can be a single base64 blob without '@'
        if proto in ("ss", "ssr"):
            try:
                decoded = b64_decode_padded(core).decode("utf-8", "replace")
                return f"{proto}|{decoded}" if "@" in decoded else None
            except Exception:
                return None
        return None
    user_host = core.split("?", 1)[0]
    if ":" not in user_host.rsplit("@", 1)[-1]:
        return None
    return f"{proto}|{user_host.lower()}"


def fetch_channel(username: str, retries: int = 3) -> str:
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"https://t.me/s/{username}", headers={"User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"fetch {username} failed after {retries} tries: {last_err}")


def clean_text(raw: str) -> str:
    raw = re.sub(r"<br\s*/?>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    text = html.unescape(raw)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip()).strip()


def parse_posts(page: str):
    marks = [(int(m.group(1)), m.start())
             for m in re.finditer(r'data-post="[^"/]+/(\d+)"', page)]
    posts = []
    for i, (pid, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(page)
        segment = page[start:end]
        tm = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', segment, re.S)
        text = clean_text(tm.group(1)) if tm else ""
        posts.append({"id": pid, "text": text})
    return posts


def write_file(path: str, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def main() -> int:
    with open(CHANNELS_FILE, encoding="utf-8") as f:
        channels = json.load(f)

    found: list[dict] = []  # {config, protocol, country, post_id, channel}
    seen: set[str] = set()
    per_channel: dict[str, dict] = {}

    for username in channels:
        try:
            page = fetch_channel(username)
        except Exception as e:
            print(f"ERROR {username}: {e}")
            per_channel[username] = {"posts": 0, "configs": 0, "error": str(e)}
            continue
        posts = parse_posts(page)
        count = 0
        # Newest post first, so newest configs win on duplicates.
        for post in sorted(posts, key=lambda p: p["id"], reverse=True):
            location = extract_location(post["text"])
            for raw in CONFIG_RE.findall(post["text"]):
                cfg = clean_config(raw)
                key = dedupe_key(cfg)
                if not key or key in seen:
                    continue
                seen.add(key)
                proto = cfg.split("://", 1)[0].lower()
                found.append({
                    "config": cfg, "protocol": proto,
                    "country": location, "post_id": post["id"],
                    "channel": username,
                })
                count += 1
        per_channel[username] = {"posts": len(posts), "configs": count}

    os.makedirs(COUNTRIES_DIR, exist_ok=True)
    # Clear stale country files from previous runs.
    for old in os.listdir(COUNTRIES_DIR):
        if old.endswith(".txt"):
            os.remove(os.path.join(COUNTRIES_DIR, old))

    by_protocol: dict[str, list[str]] = {}
    by_country: dict[str, list[str]] = {}
    for item in found:
        by_protocol.setdefault(item["protocol"], []).append(item["config"])
        by_country.setdefault(item["country"], []).append(item["config"])

    all_cfgs = [i["config"] for i in found]
    write_file(os.path.join(OUT_DIR, "all.txt"), all_cfgs)
    write_file(
        os.path.join(OUT_DIR, "all_base64.txt"),
        [base64.b64encode("\n".join(all_cfgs).encode()).decode()] if all_cfgs else [],
    )
    for proto, lines in by_protocol.items():
        fname = PROTOCOL_FILES.get(proto)
        if fname:
            write_file(os.path.join(OUT_DIR, fname), lines)
    for country, lines in by_country.items():
        fname = "unknown.txt" if country == "UNKNOWN" else f"{country}.txt"
        write_file(os.path.join(COUNTRIES_DIR, fname), lines)

    stats = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "channels": channels,
        "total": len(all_cfgs),
        "by_protocol": {p: len(v) for p, v in sorted(by_protocol.items())},
        "by_country": {c: len(v) for c, v in sorted(by_country.items())},
        "per_channel": per_channel,
    }
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
