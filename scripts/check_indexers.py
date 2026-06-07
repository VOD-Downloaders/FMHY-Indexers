#!/usr/bin/env python3

import os
import sys
import glob
import json
import time
import datetime
from urllib.parse import urlparse

import requests

#####################################################
# Configuration
#####################################################
INDEXERS_PATTERN = os.environ.get("INDEXERS_PATTERN", "v0.1/*.json")
REPORT_PATH      = os.environ.get("INDEXERS_REPORT",  "indexers_report.md")
TITLE_PATH       = os.environ.get("INDEXERS_TITLE",   "indexers_title.txt")
PR_BODY_PATH     = os.environ.get("PR_REPORT",        "pullrequest_report.md")
PR_TITLE_PATH    = os.environ.get("PR_TITLE",         "pullrequest_title.txt")

TIMEOUT, RETRIES = 15, 3
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
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

#####################################################
# Helpers
#####################################################
def remove_www_from_url(url):
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h

def url_to_string(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"

def write_indexer_specification(path, cfg):
    with open(path, "w") as f:
        json.dump(cfg, f, indent="\t")
        f.write("\n")

#####################################################
# Functions
#####################################################
def test_url(url):
    for attempt in range(RETRIES):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        except requests.Timeout:
            time.sleep(2 * (attempt + 1))
            continue
        except requests.ConnectionError:
            return ("unreachable", None)
        except requests.RequestException:
            return ("unreachable", None)

        code = response.status_code
        if code in ALIVE_BUT_REFUSING: # != dead
            return ("blocked", response.url)
        if code in (404, 410): # answering, root gone
            return ("missing", response.url)
        if code >= 500: # transient
            time.sleep(2 * (attempt + 1)) 
            continue
        if code >= 400: # missing
            return ("missing", response.url)

        # moved or live
        return ("moved" if remove_www_from_url(response.url) != remove_www_from_url(url) else "live", response.url)

    return ("down", None) # failed after retries or timed out

#####################################################
# Report
#####################################################
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
        lines.append(f"### {p['name']} — `{p['path']}`")
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

#####################################################
# Main
#####################################################
def main():
    problems, fixes = [], []

    for cfg_path in sorted(glob.glob(INDEXERS_PATTERN)):
        with open(cfg_path) as f:
            cfg = json.load(f)
        name = cfg.get("name", cfg_path)
        status, final = test_url(cfg["url"])

        if status in ("live", "blocked"):
            continue                                              # alive, leave it

        if status == "moved":                                     # -> PR
            old = cfg["url"]
            new_url = (final)
            cfg["mirrors"] = [old] + [m for m in cfg.get("mirrors", [])
                                      if url_to_string(m) != new_url]
            cfg["url"] = new_url
            write_indexer_specification(cfg_path, cfg)
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
            st, fin = test_url(m)
            mirror_results.append((m, st))
            if st in ("live", "moved", "blocked"):
                promoted = url_to_string(fin if st == "moved" else m)
                break
        if promoted:                                              # -> PR
            old = cfg["url"]
            cfg["mirrors"] = [old] + [x for x in cfg.get("mirrors", [])
                                      if url_to_string(x) != promoted]
            cfg["url"] = promoted
            write_indexer_specification(cfg_path, cfg)
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
