#!/usr/bin/env python3
"""Indexer health check.

Probes each indexer config's URL (and mirrors), then splits outcomes two ways:

  Auto-fixable -> rewrite the config file in place (picked up by the
                  create-pull-request step):
      * the URL redirects to a new host
      * the primary is unreachable but a mirror still works

  Needs a human -> recorded in the report file (turned into a GitHub issue):
      * answering but the root returns 404/410 ("missing")
      * repeated 5xx / timeouts ("down")
      * primary unreachable AND no working mirror

The script always writes the PR body + PR title files (so the workflow's
body-path / title read always resolve) and only writes the issue report +
title files when something genuinely needs attention. Exit is always 0 so a
partial set of auto-fixes still reaches the PR even when other sites are broken.

All paths are configurable via environment variables (set once in the workflow
`env:` block); the defaults let it run locally too.
"""
import os
import sys
import glob
import json
import time
import datetime
from urllib.parse import urlparse

import requests

# --- configuration (overridden by the workflow env block) -------------------
CONFIG_GLOB   = os.environ.get("INDEXERS_PATTERN", "v0.1/*.json")
REPORT_PATH   = os.environ.get("INDEXERS_REPORT",  "indexers_report.md")
TITLE_PATH    = os.environ.get("INDEXERS_TITLE",   "indexers_title.txt")
PR_BODY_PATH  = os.environ.get("PR_REPORT",        "pullrequest_report.md")
PR_TITLE_PATH = os.environ.get("PR_TITLE",         "pullrequest_title.txt")

TIMEOUT, RETRIES = 15, 3
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
}
ALIVE_BUT_REFUSING = {401, 403, 407, 429, 503}  # answered, just won't let the bot through

STATUS_DESC = {
    "live":        "alive",
    "blocked":     "alive (challenge / 403)",
    "moved":       "redirected",
    "missing":     "missing — answering, but the root returned 404/410",
    "down":        "down — repeated 5xx or timeouts (could be temporary)",
    "unreachable": "unreachable — DNS / connection / TLS failure (domain looks gone)",
}
ICON = {"missing": "⚠️", "down": "⚠️", "unreachable": "❌"}


# --- helpers ----------------------------------------------------------------
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
        json.dump(cfg, f, indent="\t")   # tabs, to match the existing files (minimal diff)
        f.write("\n")


def probe(url):
    """Return (status, final_url). status: live|moved|blocked|missing|down|unreachable."""
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        except requests.Timeout:
            time.sleep(2 * (attempt + 1)); continue   # transient; retry
        except requests.ConnectionError:
            return ("unreachable", None)              # DNS / refused / TLS = domain dead
        except requests.RequestException:
            return ("unreachable", None)

        code = r.status_code
        if code in ALIVE_BUT_REFUSING:
            return ("blocked", r.url)                 # 403 != dead
        if code in (404, 410):
            return ("missing", r.url)                 # answering, root gone
        if code >= 500:
            time.sleep(2 * (attempt + 1)); continue   # 500/502/504 likely transient
        if code >= 400:
            return ("missing", r.url)
        return ("moved" if host(r.url) != host(url) else "live", r.url)

    return ("down", None)  # exhausted retries on timeout/5xx


def write_report(problems):
    """Issue body: the indexers that could not be fixed automatically."""
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
        if p["mirrors"] is not None:              # only set for the dead-no-mirror case
            if p["mirrors"]:
                tried = ", ".join(f"`{u}` ({STATUS_DESC.get(st, st)})" for u, st in p["mirrors"])
                lines.append(f"- Mirrors tried: {tried}")
            else:
                lines.append("- No mirrors configured.")
            lines.append("- → No working mirror found; set a new domain manually.")
        lines.append("")
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))


def write_pr_body(fixes):
    """PR body: the config rewrites that were applied. Always written."""
    lines = ["## Automated indexer domain updates", ""]
    if fixes:
        lines += ["The health check rewrote these config files:", ""]
        lines += [f"- {fix}" for fix in fixes]
    else:
        lines += ["_No changes this run._"]
    lines += ["", "⚠️ Review the diff before merging — redirects from dead domains "
                  "can point at parked or malicious pages."]
    with open(PR_BODY_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


# --- main -------------------------------------------------------------------
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
            old = cfg["url"]
            new_url = canonical(final)
            cfg["mirrors"] = [old] + [m for m in cfg.get("mirrors", [])
                                      if canonical(m) != new_url]
            cfg["url"] = new_url
            write_config(cfg_path, cfg)
            fixes.append(f"**{name}** (`{cfg_path}`): redirected `{old}` → `{new_url}` "
                         "— old domain moved into `mirrors`.")
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
            old = cfg["url"]
            cfg["mirrors"] = [old] + [x for x in cfg.get("mirrors", [])
                                      if canonical(x) != promoted]
            cfg["url"] = promoted
            write_config(cfg_path, cfg)
            fixes.append(f"**{name}** (`{cfg_path}`): primary `{old}` unreachable "
                         f"→ promoted mirror `{promoted}`.")
        else:                                                     # -> issue
            problems.append({"name": name, "path": cfg_path, "url": cfg["url"],
                             "status": status, "mirrors": mirror_results})

    for line in fixes:
        print("FIX:", line)

    # PR files: always written so the workflow's body-path / title read resolve.
    write_pr_body(fixes)
    n = len(fixes)
    pr_title = (f"[Chore] Update {n} indexer domain{'s' if n != 1 else ''}"
                if fixes else "[Chore] No indexer changes")
    with open(PR_TITLE_PATH, "w") as f:
        f.write(pr_title)

    # Issue files: only written when something actually needs a human.
    if problems:
        names = sorted({p["name"] for p in problems})
        subjects = (", ".join(names) if len(names) <= 3
                    else ", ".join(names[:3]) + f" +{len(names) - 3} more")
        issue_title = f"🔧 Indexer health: {subjects} need attention"
        with open(TITLE_PATH, "w") as f:
            f.write(issue_title)
        write_report(problems)
        print(f"{len(problems)} indexer(s) need manual attention — report + title written.")
    else:
        print("Nothing needs manual attention.")

    sys.exit(0)


if __name__ == "__main__":
    main()
