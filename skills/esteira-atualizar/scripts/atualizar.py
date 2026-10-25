#!/usr/bin/env python3
"""Atualiza a esteira de um projeto a partir do repositório, sem perder as mudanças feitas aqui.

  atualizar.py check [--repo URL]        versão instalada × última da main (JSON)
  atualizar.py prepare [--repo URL]      clona o repositório e faz o merge de 3 vias de cada arquivo
                                         num diretório de trabalho; não toca no projeto
  atualizar.py apply --work <dir>        grava no projeto o resultado do prepare (com os conflitos já
                                         resolvidos), atualiza .claude/esteira-versao.json e apaga <dir>

A versão instalada é o commit da main gravado em .claude/esteira-versao.json (o install.sh e o apply
gravam). Para cada arquivo da esteira, o prepare compara três versões: a do commit instalado (base),
a do projeto (local) e a da main (novo). O que o projeto não mudou recebe o novo; o que só o projeto
mudou fica como está; o que os dois mudaram é mesclado (`git merge-file`) e, se as mudanças batem
na mesma linha, vira conflito para resolver em <work>/resultado/ antes do apply.

Arquivos acompanhados: skills/esteira-*/ → .claude/skills/ e, se a esteira já foi configurada,
skills/esteira-bootstrap/pipeline/ → .claude/esteira/ (menos config.json e hooks/). Sem o arquivo
de versão (instalação antiga), a base é estimada: o commit da main mais parecido com o projeto.
Toda saída é JSON.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
SKILLS = HERE.parents[2]                               # .../.claude/skills
TARGET = SKILLS.parents[1]
VERSION = TARGET / ".claude" / "esteira-versao.json"
DEPLOY = TARGET / ".claude" / "esteira"
DEFAULT_REPO = "https://github.com/guilhermefeitosa66/esteira.git"
BRANCH = "main"
KEEP = {"config.json", "hooks"}                        # de .claude/esteira/, nunca acompanhados
MARKER = re.compile(r"^(<<<<<<< local|>>>>>>> novo)$", re.M)


def out(data, code=0):
    print(json.dumps(data, indent=1, ensure_ascii=False))
    sys.exit(code)


def git(*args, cwd=None, raw=False):
    r = subprocess.run(["git", *args], capture_output=True, cwd=cwd)
    if r.returncode != 0:
        out({"erro": f"git {' '.join(args[:3])}: {r.stderr.decode(errors='replace').strip()}"}, 1)
    return r.stdout if raw else r.stdout.decode().strip()


def blob_sha(path):
    """O sha1 que o git daria ao arquivo (None se não existe), para comparar sem ler do clone."""
    if not path.is_file():
        return None
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def version():
    try:
        return json.loads(VERSION.read_text())
    except (OSError, ValueError):
        return {}


def repo_url(a):
    return a.repo or version().get("repositorio") or DEFAULT_REPO


def tree(clone, commit):
    """{caminho no repositório: (modo, sha)} das skills num commit."""
    t = {}
    for line in git("ls-tree", "-r", commit, "--", "skills", cwd=clone).splitlines():
        meta, path = line.split("\t", 1)
        mode, _, sha = meta.split()
        t[path] = (mode, sha)
    return t


def mapping(paths):
    """{caminho no projeto: caminho no repositório} para os arquivos acompanhados."""
    deployed = (DEPLOY / "config.json").exists()
    m = {}
    for p in paths:
        parts = p.split("/")
        if len(parts) < 3 or not parts[1].startswith("esteira-"):
            continue
        m[".claude/skills/" + "/".join(parts[1:])] = p
        if deployed and parts[1:3] == ["esteira-bootstrap", "pipeline"] and len(parts) > 3 and parts[3] not in KEEP:
            m[".claude/esteira/" + "/".join(parts[3:])] = p
    return m


def estimate_base(clone, new):
    """Sem arquivo de versão: o commit da main cujos arquivos mais batem com os do projeto."""
    best, score = None, -1
    for commit in git("rev-list", new, cwd=clone).splitlines():
        t = tree(clone, commit)
        s = sum(1 for local, r in mapping(t).items() if blob_sha(TARGET / local) == t[r][1])
        if s > score:                                  # rev-list vem do mais novo: empate fica com ele
            best, score = commit, s
    return best


# --- check -----------------------------------------------------------------------

def check(a):
    url = repo_url(a)
    ref = subprocess.run(["git", "ls-remote", url, f"refs/heads/{BRANCH}"], capture_output=True, text=True)
    if ref.returncode != 0 or not ref.stdout.strip():
        out({"erro": f"não consegui ler {url}: {ref.stderr.strip()}"}, 1)
    latest = ref.stdout.split()[0]
    v = version()
    out({"repositorio": url, "instalada": v.get("commit"), "instalada_em": v.get("atualizado_em"),
         "ultima": latest, "atualizado": v.get("commit") == latest,
         "sem_arquivo_de_versao": not v, "projeto": str(TARGET)})


# --- prepare ---------------------------------------------------------------------

def prepare(a):
    url = repo_url(a)
    work = Path(tempfile.mkdtemp(prefix="esteira-atualizar-"))
    clone = work / "repositorio"
    git("clone", "--quiet", "--no-checkout", "--branch", BRANCH, url, str(clone))
    new = git("rev-parse", "HEAD", cwd=clone)
    base, estimated = version().get("commit"), False
    if not base or subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], cwd=clone,
                                  capture_output=True).returncode != 0:
        base, estimated = estimate_base(clone, new), True
    bt, nt = tree(clone, base), tree(clone, new)
    bm, nm = mapping(bt), mapping(nt)

    res, conf = work / "resultado", work / "conflitos"
    plan = []
    for local in sorted(set(bm) | set(nm)):
        r = nm.get(local) or bm[local]
        b, n = bt.get(r, (None, None))[1], nt.get(r, (None, None))[1]
        lp = TARGET / local
        lsha = blob_sha(lp)
        if lsha == n or b == n:                        # já igual ao novo, ou o repositório não mudou
            continue
        entry = {"arquivo": local, "local_sha": lsha, "executavel": nt.get(r, ("",))[0] == "100755"}
        dest = res / local
        dest.parent.mkdir(parents=True, exist_ok=True)
        new_data = git("cat-file", "blob", n, cwd=clone, raw=True) if n else None
        if lsha == b:                                  # o projeto não mexeu: vem o novo
            entry["acao"] = "remover" if n is None else ("adicionar" if b is None else "atualizar")
            if new_data is not None:
                dest.write_bytes(new_data)
        elif lsha is None:                             # apagado aqui, mudou lá: fica apagado até decidir
            entry["acao"] = "decidir:apagado-aqui-mudou-no-repositorio"
            (conf / local).parent.mkdir(parents=True, exist_ok=True)
            (conf / (local + ".novo")).write_bytes(new_data)
        elif n is None:                                # mudou aqui, apagado lá: fica até decidir
            entry["acao"] = "decidir:mudou-aqui-apagado-no-repositorio"
            dest.write_bytes(lp.read_bytes())
        else:
            base_data = git("cat-file", "blob", b, cwd=clone, raw=True) if b else b""
            local_data = lp.read_bytes()
            c = conf / local
            c.parent.mkdir(parents=True, exist_ok=True)
            for suffix, data in (("local", local_data), ("base", base_data), ("novo", new_data)):
                Path(f"{c}.{suffix}").write_bytes(data)
            if any(b"\0" in d for d in (local_data, base_data, new_data)):
                entry["acao"] = "conflito"
                entry["binario"] = True
                dest.write_bytes(local_data)
            else:
                m = subprocess.run(["git", "merge-file", "-p", "--diff3", "-L", "local", "-L", "base", "-L", "novo",
                                    f"{c}.local", f"{c}.base", f"{c}.novo"], capture_output=True)
                if m.returncode < 0 or m.returncode > 127:
                    out({"erro": f"git merge-file {local}: {m.stderr.decode(errors='replace')}"}, 1)
                dest.write_bytes(m.stdout)
                entry["acao"] = "mesclado" if m.returncode == 0 else "conflito"
                if m.returncode:
                    entry["trechos_em_conflito"] = m.returncode
        plan.append(entry)

    meta = {"repositorio": url, "base": base, "base_estimada": estimated, "novo": new, "projeto": str(TARGET)}
    (work / "plano.json").write_text(json.dumps({**meta, "arquivos": plan}, indent=1, ensure_ascii=False) + "\n")
    (work / "mudancas.diff").write_bytes(git("diff", base, new, "--", "skills", cwd=clone, raw=True))
    by = {}
    for e in plan:
        by.setdefault(e["acao"], []).append(e["arquivo"])
    out({**meta, "work": str(work),
         "commits_novos": git("log", "--format=%h %ad %s", "--date=short", f"{base}..{new}", cwd=clone).splitlines(),
         "por_acao": by,
         "pendentes": [e["arquivo"] for e in plan if e["acao"] == "conflito" or e["acao"].startswith("decidir:")],
         "scripts_do_pipeline_mudam": any(e["arquivo"].startswith(".claude/esteira/") for e in plan),
         "diff_do_repositorio": str(work / "mudancas.diff"),
         "resultado": str(res), "conflitos": str(conf)})


# --- apply -----------------------------------------------------------------------

def apply(a):
    work = Path(a.work)
    try:
        plan = json.loads((work / "plano.json").read_text())
    except (OSError, ValueError):
        out({"erro": f"{work}/plano.json não existe: rode o prepare"}, 1)
    if plan["projeto"] != str(TARGET):
        out({"erro": f"o plano é de {plan['projeto']}, não deste projeto"}, 1)
    changed, markers = [], []
    for e in plan["arquivos"]:
        if blob_sha(TARGET / e["arquivo"]) != e["local_sha"]:
            changed.append(e["arquivo"])
        r = work / "resultado" / e["arquivo"]
        if r.is_file() and MARKER.search(r.read_text(errors="replace")):
            markers.append(e["arquivo"])
    if changed:
        out({"erro": "arquivos mudaram no projeto depois do prepare; rode o prepare de novo", "arquivos": changed}, 1)
    if markers:
        out({"erro": "ainda há marcas de conflito em resultado/", "arquivos": markers}, 1)

    written, removed = [], []
    for e in plan["arquivos"]:
        src, dst = work / "resultado" / e["arquivo"], TARGET / e["arquivo"]
        if src.is_file():                              # o estado final é o que está em resultado/
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".esteira-tmp")
            tmp.write_bytes(src.read_bytes())
            mode = dst.stat().st_mode & 0o777 if dst.exists() else 0o644
            os.chmod(tmp, mode | 0o111 if e["executavel"] else mode)
            os.replace(tmp, dst)
            written.append(e["arquivo"])
        elif dst.exists():
            dst.unlink()
            removed.append(e["arquivo"])
            d = dst.parent
            while d != TARGET and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
    VERSION.write_text(json.dumps({"repositorio": plan["repositorio"], "branch": BRANCH, "commit": plan["novo"],
                                   "atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                  indent=1, ensure_ascii=False) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    out({"versao": plan["novo"], "gravados": written, "removidos": removed,
         "reiniciar_loops": any(f.startswith(".claude/esteira/") for f in written + removed),
         "skills_novas": sorted(e["arquivo"].split("/")[2] for e in plan["arquivos"] if e["acao"] == "adicionar"
                                and re.fullmatch(r"\.claude/skills/[^/]+/SKILL\.md", e["arquivo"]))})


def main():
    if SKILLS.name != "skills" or SKILLS.parent.name != ".claude":
        out({"erro": "rode a partir do .claude/skills/esteira-atualizar do projeto"}, 1)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "prepare"):
        sub.add_parser(name).add_argument("--repo", help="outro repositório (um fork, por exemplo)")
    sub.add_parser("apply").add_argument("--work", required=True)
    a = ap.parse_args()
    {"check": check, "prepare": prepare, "apply": apply}[a.cmd](a)


if __name__ == "__main__":
    main()
