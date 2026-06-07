#!/usr/bin/env python3
"""Probe indexer URLs.

Outcomes:
  * redirected, or primary dead but a mirror works -> rewrite the config in place
    (picked up by the create-pull-request step)
  * answering-but-broken (404/410), down (5xx/timeout), or dead with no working
    mirror -> recorded in attention_report.md (turned into a GitHub issue)
Exit is always 0 so auto-fixes still reach the PR even when other sites need a human.
"""
import json, glob, sys, time, os, datetime
from urllib.parse import urlparse
import requests

CONFIG_GLOB = os.environ.get("INDEXERS_PATTERN", "v0.1/*.json")
REPORT_PATH = "attention_report.md"
TIMEOUT, RETRIES = 15, 3
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
}
ALIVE_BUT_REFUSING = {401, 403, 407, 429, 503}  # answered, just won't let the bot through

STATUS_DESC = {
    "missing":     "missing — answering, but the root returned 404/410",
    "down":        "down — repeated 5xx or timeouts (could be temporary)",
    "unreachable": "unreachable — DNS / connection / TLS failure (domain looks gone)",
    "blocked":     "alive (challenge / 403)",
    "live":        "alive",
    "moved":       "redirected",
}
ICON = {"missing": "⚠️", "down": "⚠️", "unreachable": "❌"}


def host(url):
    """www-stripped host, for deciding whether the domain actually changed."""
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def canonical(url):
    """Rebuild as scheme://host/ to match the 'https://www.x/' config style."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


def write_config(path, cfg):
    with open(path, "w") as f:
        json.dump(cfg, f, indent="\t")   # tabs, to match existing files (minimal diff)
        f.write("\n")


def probe(url):
    """Return (status, final_url). status: live|moved|blocked|missing|down|unreachable."""
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        except (requests.ConnectionError, requests.exceptions.SSLError):
            return ("unreachable", None)              # no server there = domain dead
        except requests.Timeout:
            time.sleep(2 * (attempt + 1)); continue   # transient; retry
        except requests.RequestException:
            return ("unreachable", None)

        code = r.status_code
        if code in ALIVE_BUT_REFUSING:
            return ("blocked", r.url)                 # 403 != dead
        if code in (404, 410):
            return ("missing", r.url)
        if code >= 500:
            time.sleep(2 * (attempt + 1)); continue   # 500/502/504 likely transient
        if code >= 400:
            return ("missing", r.url)
        return ("moved" if host(r.url) != host(url) else "live", r.url)

    return ("down", None)  # exhausted retries on timeout/5xx


def write_report(problems):
    now = datetime.datetime.now(datetime.timezone.utc)
    lines = [
        "## 🔧 Indexer health check — manual attention needed", "",
        f"_Generated {now:%Y-%m-%d %H:%M UTC}_", "",
        "Redirects and working-mirror swaps are handled automatically via PR. "
        "The indexers below could **not** be fixed safely and need a human.", "",
    ]
    for p in problems:
        lines.append(f"### {ICON.get(p['status'], '⚠️')} {p['name']} — `{p['path']}`")
        lines.append(f"- Primary `{p['url']}` → **{STATUS_DESC[p['status']]}**")
        if p["mirrors"] is not None:          # only set for the dead-no-mirror case
            if p["mirrors"]:
                tried = ", ".join(f"`{u}` ({STATUS_DESC.get(st, st)})" for u, st in p["mirrors"])
                lines.append(f"- Mirrors tried: {tried}")
            else:
                lines.append("- No mirrors configured.")
            lines.append("- → No working mirror found; set a new domain manually.")
        lines.append("")
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))


def main():
    problems, fixes = [], []

    for cfg_path in sorted(glob.glob(CONFIG_GLOB)):
        with open(cfg_path) as f:
            cfg = json.load(f)
        name = cfg.get("name", cfg_path)
        status, final = probe(cfg["url"])

        if status in ("live", "blocked"):
            continue                                              # alive, leave it

        if status == "moved":                                     # -> PR
            new_url = canonical(final)
            cfg["mirrors"] = [cfg["url"]] + [m for m in cfg.get("mirrors", [])
                                             if canonical(m) != new_url]
            cfg["url"] = new_url
            write_config(cfg_path, cfg)
            fixes.append(f"{name}: redirected → {new_url}")
            continue

        if status in ("missing", "down"):                         # -> issue
            problems.append({"name": name, "path": cfg_path, "url": cfg["url"],
                             "status": status, "mirrors": None})
            continue

        # status == "unreachable": try to promote a working mirror
        mirror_results, promoted = [], None
        for m in cfg.get("mirrors", []):
            st, fin = probe(m)
            mirror_results.append((m, st))
            if st in ("live", "moved", "blocked"):
                promoted = canonical(fin if st == "moved" else m)
                break
        if promoted:                                              # -> PR
            cfg["mirrors"] = [cfg["url"]] + [x for x in cfg.get("mirrors", [])
                                             if canonical(x) != promoted]
            cfg["url"] = promoted
            write_config(cfg_path, cfg)
            fixes.append(f"{name}: primary unreachable → promoted mirror {promoted}")
        else:                                                     # -> issue
            problems.append({"name": name, "path": cfg_path, "url": cfg["url"],
                             "status": status, "mirrors": mirror_results})

    for f in fixes:
        print("FIX:", f)
    if problems:
        write_report(problems)
        print(f"{len(problems)} indexer(s) need manual attention — report written.")
    else:
        print("Nothing needs manual attention.")
    sys.exit(0)


if __name__ == "__main__":
    main()
