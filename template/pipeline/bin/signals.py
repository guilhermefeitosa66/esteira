#!/usr/bin/env python3
"""Deterministic red flags in an issue or a pull request, before any LLM reads it.

  signals.py issue <N>
  signals.py pr <N>

Prints JSON: the author's standing (association, account age, public repos)
and a list of findings, each {"kind", "where", "excerpt"}. A finding is a
reason to look closer, never a verdict on its own -- an issue that quotes an
error log can trip "shell" without being hostile.
"""
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

CFG = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text())
REPO = CFG["repo"]
# Links to these hosts are ordinary in an issue; anything else is worth a closer look.
TRUSTED = ["github.com", "raw.githubusercontent.com", "user-images.githubusercontent.com", "github.io",
           "www.w3.org", "creativecommons.org"] + CFG.get("trusted_domains", [])

TEXT_RULES = [
    ("prompt-injection", r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|all|earlier|system)\b.{0,20}\b(instructions?|prompts?|rules?|context)\b"),
    ("prompt-injection", r"\b(system prompt|developer message|you are (now )?(an? )?(ai|assistant|llm|language model|claude|chatgpt|agent))\b"),
    ("prompt-injection", r"\b(as an ai|dear (ai|assistant|claude|llm|agent|bot)|note to (the )?(ai|llm|agent|assistant)|if you are an? (ai|llm|agent))\b"),
    ("prompt-injection", r"</?(system|assistant|user|instructions?|tool_call|function_call|antml)[^>]*>"),
    ("tool-steering", r"\b(run|execute|call|invoke)\b.{0,30}\b(bash|shell|terminal|command|gh |git push|curl|wget|tool)\b"),
    ("shell", r"(curl|wget)[^\n|]{0,200}\|\s*(ba|z)?sh\b|\bbase64\s+-d\b|\beval\s*\(|\brm\s+-rf\s+[~/]|\bchmod\s+\+x\b|\bnc\s+-e\b"),
    ("secrets", r"(\.ssh/|id_rsa|id_ed25519|\.env\b|GITHUB_TOKEN|GH_TOKEN|api[_-]?key|secret|password|credentials?|\.netrc|\.gnupg|keyring)"),
    ("workflow", r"\.github/workflows|pull_request_target|secrets\.\w+|ACTIONS_RUNTIME"),
    ("exfil", r"https?://(?!(" + "|".join(re.escape(d) for d in TRUSTED) + r")\b)[\w.-]+\.[a-z]{2,}[^\s)>\]]*"),
    ("blob", r"[A-Za-z0-9+/]{120,}={0,2}"),
]
HIDDEN_RULES = [
    ("hidden-html-comment", r"<!--.*?-->"),
    ("hidden-details", r"<details>.*?</details>"),
    ("hidden-style", r"<(span|div|p)[^>]+(display\s*:\s*none|font-size\s*:\s*0|color\s*:\s*(white|#fff))"),
]
DIFF_PATHS = [
    ("ci-or-release", r"^\.github/|^\.gitlab-ci|^packaging/|^deploy/|^infra/|^Makefile$|^Dockerfile|^docker-compose|^scripts/|\.spec$|^vendor/"),
    ("dependencies", r"(^|/)(requirements[^/]*\.(txt|lock)|pyproject\.toml|poetry\.lock|uv\.lock|setup\.(py|cfg)|package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|go\.(mod|sum)|Cargo\.(toml|lock)|Gemfile(\.lock)?|composer\.(json|lock)|build\.gradle(\.kts)?|pom\.xml)$"),
    ("binary", r"\.(so|dll|exe|bin|AppImage|whl|zip|tar|gz|xz|jar|pyc)$"),
    ("agent-config", r"(^|/)(CLAUDE|AGENTS)\.md$|^\.claude/|^\.github/copilot"),
]
DIFF_CODE = [
    ("exec", r"^\+.*\b(subprocess|os\.system|os\.popen|exec\(|eval\(|compile\(|__import__|importlib\.import_module|pty\.spawn|child_process|execSync|spawn\(|new Function\(|Runtime\.getRuntime|ProcessBuilder|exec\.Command|shell_exec|system\()"),
    ("network", r"^\+.*\b(urllib|requests\.|http\.client|socket\.|urlopen|fetch\(|axios|XMLHttpRequest|WebSocket|net/http|HttpClient|curl|wget)\b"),
    ("obfuscation", r"^\+.*\b(base64|codecs\.decode|marshal|zlib\.decompress|bytes\.fromhex|rot13|chr\(\d+\)\s*\+|atob\(|Buffer\.from\([^)]*base64|String\.fromCharCode)"),
    ("fs-outside", r"^\+.*(expanduser\([\"']~/?\.(ssh|gnupg|config|local)|/etc/|\.bashrc|\.zshrc|\.profile|crontab|systemd/user)"),
]


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def invisible(text):
    out = []
    for ch in set(text):
        cat = unicodedata.category(ch)
        if cat == "Cf" or ch in "‪‫‬‭‮⁦⁧⁨⁩":
            out.append(f"U+{ord(ch):04X}")
    return out


def scan(text, where):
    found = []
    for kind, rx in TEXT_RULES:
        for m in re.finditer(rx, text, re.I):
            found.append({"kind": kind, "where": where, "excerpt": m.group(0)[:160]})
    for kind, rx in HIDDEN_RULES:
        for m in re.finditer(rx, text, re.I | re.S):
            found.append({"kind": kind, "where": where, "excerpt": m.group(0)[:300]})
    inv = invisible(text)
    if inv:
        found.append({"kind": "invisible-chars", "where": where, "excerpt": " ".join(sorted(inv))})
    return found


def author(login):
    try:
        u = json.loads(gh("api", f"users/{login}"))
    except subprocess.CalledProcessError:
        return {"login": login}
    created = datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))
    return {"login": login, "type": u.get("type"),
            "account_age_days": (datetime.now(timezone.utc) - created).days,
            "public_repos": u.get("public_repos"), "followers": u.get("followers"),
            "maintainer": login in CFG["maintainers"]}


def issue(n):
    i = json.loads(gh("issue", "view", str(n), "--repo", REPO, "--json",
                      "title,body,author,comments"))
    i["authorAssociation"] = json.loads(gh("api", f"repos/{REPO}/issues/{n}"))["author_association"]
    found = scan(i["title"], "title") + scan(i["body"] or "", "body")
    for k, c in enumerate(i["comments"]):
        if c["author"]["login"] not in CFG["maintainers"]:
            found += scan(c["body"], f"comment {k + 1} by {c['author']['login']}")
    return {"issue": n, "author": author(i["author"]["login"]),
            "association": i.get("authorAssociation"), "findings": found}


def pr(n):
    p = json.loads(gh("pr", "view", str(n), "--repo", REPO, "--json",
                      "title,body,author,files,isCrossRepository,commits"))
    p["authorAssociation"] = json.loads(gh("api", f"repos/{REPO}/pulls/{n}"))["author_association"]
    found = scan(p["title"], "title") + scan(p["body"] or "", "body")
    for f in p["files"]:
        for kind, rx in DIFF_PATHS:
            if re.search(rx, f["path"]):
                found.append({"kind": kind, "where": f["path"], "excerpt": f"+{f['additions']}/-{f['deletions']}"})
    diff = gh("pr", "diff", str(n), "--repo", REPO)
    current = "?"
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        for kind, rx in DIFF_CODE:
            if re.search(rx, line):
                found.append({"kind": kind, "where": current, "excerpt": line[:200]})
        if line.startswith("+"):
            for f in scan(line[1:], current):
                if f["kind"] in ("prompt-injection", "invisible-chars", "hidden-html-comment", "exfil", "shell"):
                    found.append(f)
    return {"pr": n, "author": author(p["author"]["login"]), "association": p.get("authorAssociation"),
            "cross_repository": p["isCrossRepository"], "files": len(p["files"]),
            "commits": len(p["commits"]), "findings": found}


def summarize(result):
    """Group findings by kind: a count and a few samples, not hundreds of lines."""
    groups = {}
    for f in result.pop("findings"):
        g = groups.setdefault(f["kind"], {"count": 0, "samples": []})
        g["count"] += 1
        if len(g["samples"]) < 5:
            g["samples"].append(f)
    result["findings"] = groups
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("issue", "pr"):
        sys.exit(__doc__)
    result = (issue if sys.argv[1] == "issue" else pr)(int(sys.argv[2]))
    print(json.dumps(summarize(result), indent=1))
