# V2Ray Configs — collected from Telegram

Configs are collected automatically from public Telegram channels and
published here as plain text files, every 30 minutes.

> Source (for now): [@persianvpnhub](https://t.me/persianvpnhub)
> To add a channel, add its username to `channels.json` — no code change needed.

## Subscription (copy into V2RayNG, Streisand, FoXray, …)

```
https://raw.githubusercontent.com/rzashakeri/v2ray-configs/main/configs/all_base64.txt
```

## Files

| File | What it is |
| --- | --- |
| `configs/all.txt` | Every config, newest first |
| `configs/all_base64.txt` | Same list, base64 — the subscription file |
| `configs/vless.txt` | VLESS only |
| `configs/vmess.txt` | VMess only |
| `configs/trojan.txt` | Trojan only |
| `configs/shadowsocks.txt` | Shadowsocks only |
| `configs/tuic.txt` / `configs/hysteria2.txt` | TUIC / Hysteria2, when the channel posts them |
| `configs/countries/<CODE>.txt` | Per country, e.g. `DE.txt`, `US.txt`, `NL.txt` |
| `configs/countries/unknown.txt` | Configs with no recognizable location |
| `stats.json` | Counts per protocol / country + last update time |

## How it works

`.github/workflows/collect.yml` runs `collect.py` every 30 minutes.
The script fetches each channel's public web view (`https://t.me/s/<channel>`,
no Telegram API key), extracts configs with a regex, drops duplicates
(same server + user, even under a different name), reads the country from
the post header (`📍 لوکیشن: آلمان 🇩🇪`), and commits the result — only
when something actually changed.

Notes / limits:

- `t.me/s` only shows about the last 20 posts per channel, so the 30-minute
  schedule is what keeps configs from being missed. It is not a permanent
  archive — configs die fast, the files always hold the freshest ones.
- Location comes from the channel's own post header, not from IP lookup.
- Posts that are files (e.g. NapsternetV) instead of config text are skipped.
