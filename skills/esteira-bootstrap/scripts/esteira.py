#!/usr/bin/env python3
"""Instalador da esteira num projeto. Só biblioteca padrão; fala com o GitHub só pelo `gh`.

  esteira.py check                      pré-requisitos (JSON); sai 1 se faltar algo obrigatório
  esteira.py projects                   projetos (boards) do dono do repositório, para escolher
  esteira.py install                    copia os scripts do pipeline para .claude/esteira/ (preserva o config)
  esteira.py configure --board new|<número> [--title T] --visibility public|private
                       --merge-on-qa yes|no --language en|pt-BR [--base <branch>]
                       [--maintainers a,b] [--evidence-repo dono/nome|none]
                                        cria/adota o board, as colunas, as labels e o repositório de
                                        evidências, e grava .claude/esteira/config.json

O projeto é a pasta que tem o `.claude/skills/` onde as skills da esteira foram copiadas: a raiz de
um repositório ou, num monorepo, a subpasta de um dos projetos. Toda saída é JSON.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
SKILLS = HERE.parents[2]                               # .../.claude/skills
PIPELINE = HERE.parents[1] / "pipeline"                # o que vira .claude/esteira/
# O projeto é a pasta acima de .claude/skills; fora dela (rodando do clone), a pasta atual.
TARGET = SKILLS.parents[1] if SKILLS.parent.name == ".claude" else Path.cwd()
DEST = TARGET / ".claude" / "esteira"

COLUMNS = [
    ("Backlog", "GRAY", "Ainda fora do pipeline"),
    ("Planning queue", "BLUE", "Esperando o plano técnico"),
    ("Planning", "BLUE", "Plano técnico em andamento"),
    ("Dev queue", "GREEN", "Esperando implementação"),
    ("In development", "GREEN", "Implementação em andamento"),
    ("Review queue", "YELLOW", "Esperando revisão de código"),
    ("In review", "YELLOW", "Revisão de código em andamento"),
    ("QA queue", "ORANGE", "Esperando QA"),
    ("In QA", "ORANGE", "QA em andamento"),
    ("Ready for release", "PURPLE", "Aprovado no QA: homologação do mantenedor"),
    ("Released", "PURPLE", "Publicado"),
    ("Needs maintainer", "RED", "Precisa de uma decisão humana"),
]
QUARANTINE = ("Future ideas", "GRAY", "Ideias guardadas para o futuro")
LABELS = {
    "triaged": ("0e8a16", "Passed triage; the pipeline may work on it"),
    "community-report": ("c5def5", "Reported or contributed by the community"),
    "bug": ("d73a4a", "Something is not working"),
    "feature": ("a2eeef", "New feature or request"),
    "documentation": ("0075ca", "Documentation"),
    "epic": ("3e4b9e", "Umbrella issue split into sub-issues; the work happens in the sub-issues"),
    "question": ("d876e3", "Question or support request"),
    "duplicate": ("cfd3d7", "Duplicate of another issue"),
}


def run(*cmd, check=True, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if check and r.returncode != 0:
        sys.exit(json.dumps({"erro": f"{' '.join(cmd[:4])}: {(r.stderr or r.stdout).strip()}"}, ensure_ascii=False))
    return r


def gh_json(*args):
    return json.loads(run("gh", *args).stdout or "null")


def graphql(query, **v):
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, val in v.items():
        args += ["-F" if isinstance(val, int) else "-f", f"{k}={val}"]
    return gh_json(*args)["data"]


def out(data, code=0):
    print(json.dumps(data, indent=1, ensure_ascii=False))
    sys.exit(code)


# --- check ---------------------------------------------------------------------

def have(binary):
    return shutil.which(binary) is not None


def check():
    items, missing = [], False

    def item(name, ok, required, hint=""):
        nonlocal missing
        items.append({"item": name, "ok": ok, "obrigatorio": required, "como_resolver": "" if ok else hint})
        if required and not ok:
            missing = True

    item("git", have("git"), True, "instale o git pelo gerenciador de pacotes")
    item("python3 >= 3.10", sys.version_info >= (3, 10), True, "instale Python 3.10 ou mais novo")
    item("flock (util-linux)", have("flock"), True, "sudo apt install util-linux  /  sudo dnf install util-linux")
    item("claude (Claude Code)", have("claude"), True, "curl -fsSL https://claude.ai/install.sh | bash")
    item("herdr", have("herdr"), True, "instale o Herdr: https://github.com/herdrdev/herdr (releases)")
    item("dentro do Herdr (HERDR_ENV=1)", os.environ.get("HERDR_ENV") == "1", True,
         "abra o Herdr, entre na pasta do projeto, rode `claude` e chame /esteira-bootstrap de lá")
    gh_ok = have("gh")
    item("gh (GitHub CLI)", gh_ok, True, "https://cli.github.com (sudo apt install gh / sudo dnf install gh)")
    if gh_ok:
        st = run("gh", "auth", "status", check=False)
        text = st.stdout + st.stderr
        item("gh autenticado", st.returncode == 0, True, "gh auth login")
        scopes = re.search(r"Token scopes:\s*(.*)", text)
        has_project = bool(scopes and re.search(r"'project'", scopes.group(1)))
        item("gh com escopo 'project'", has_project, True, "gh auth refresh -s project")
        user = run("gh", "api", "user", "--jq", ".login", check=False).stdout.strip()
        items.append({"item": "conta gh ativa", "ok": bool(user), "valor": user})
    repo = run("gh", "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef,isFork",
               check=False, cwd=TARGET) if gh_ok else None
    if repo and repo.returncode == 0:
        r = json.loads(repo.stdout)
        items.append({"item": "repositório", "ok": True, "valor": r["nameWithOwner"],
                      "visibilidade": r["visibility"].lower(), "branch_padrao": r["defaultBranchRef"]["name"]})
    else:
        item("repositório GitHub nesta pasta", False, True,
             "rode a partir da raiz de um repositório git com remoto no GitHub")
    item("docker (opcional)", have("docker"), False, "só se o projeto usar containers nos testes")
    video = SKILLS / "esteira-qa/scripts/preparar-video.sh"
    v = run(str(video), "verificar", check=False)
    items.append({"item": "ferramentas do vídeo do QA (opcional, recomendado)", "ok": v.returncode == 0,
                  "detalhe": v.stdout.strip().splitlines(),
                  "como_resolver": "" if v.returncode == 0 else f"{video} instalar"})
    out({"ok": not missing, "itens": items}, 1 if missing else 0)


# --- projects ------------------------------------------------------------------

def repo_info():
    return json.loads(run("gh", "repo", "view", "--json", "nameWithOwner,owner,visibility,defaultBranchRef,name",
                          cwd=TARGET).stdout)


def projects():
    owner = repo_info()["owner"]["login"]
    data = gh_json("project", "list", "--owner", owner, "--format", "json", "--limit", "50")
    out({"dono": owner, "projetos": [{"numero": p["number"], "titulo": p["title"], "url": p.get("url")}
                                     for p in data.get("projects", [])]})


# --- install -------------------------------------------------------------------

def git_root():
    r = run("git", "rev-parse", "--show-toplevel", check=False, cwd=TARGET)
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def install():
    root = git_root()
    if not root:
        out({"erro": f"{TARGET} não está dentro de um repositório git"}, 1)
    if SKILLS.parent.name != ".claude":
        out({"erro": "copie a pasta skills/ da esteira para o .claude/skills do projeto e rode de lá "
                     "(veja o README)"}, 1)
    faltam = [s for s in ("esteira-planejamento", "esteira-dev", "esteira-revisao", "esteira-qa",
                          "esteira-fila", "esteira-criar-issue") if not (SKILLS / s / "SKILL.md").exists()]
    if faltam:
        out({"erro": f"faltam skills em {SKILLS}: {faltam}; copie a pasta skills/ inteira"}, 1)
    DEST.mkdir(parents=True, exist_ok=True)
    keep = {"config.json", "hooks"}
    copied = []
    for item in PIPELINE.iterdir():
        target = DEST / item.name
        if item.name in keep and target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
        copied.append(str(target.relative_to(TARGET)))
    # O config tem caminhos desta máquina: fica fora do git sem mexer no .gitignore (exclude é local).
    common = Path(run("git", "rev-parse", "--git-common-dir", cwd=TARGET).stdout.strip())
    exclude = (common if common.is_absolute() else TARGET / common) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    pattern = "/" + str(DEST.relative_to(root)) + "/"
    lines = exclude.read_text().splitlines() if exclude.exists() else []
    if pattern not in lines:
        exclude.write_text("\n".join(lines + [pattern]) + "\n")
    out({"projeto": str(TARGET), "instalado": copied, "git_exclude": pattern,
         "subpasta_no_repo": str(TARGET.relative_to(root)) if TARGET != root else ""})


# --- configure -----------------------------------------------------------------

def owner_type(login):
    t = gh_json("api", f"users/{login}")["type"]
    return "organization" if t == "Organization" else "user"


def fields(number, owner):
    return gh_json("project", "field-list", str(number), "--owner", owner, "--format", "json", "--limit", "50")["fields"]


def set_options(field_id, wanted):
    q = """mutation($id:ID!,$opts:[ProjectV2SingleSelectFieldOptionInput!]){
      updateProjectV2Field(input:{fieldId:$id, singleSelectOptions:$opts}){ projectV2Field{ ... on ProjectV2SingleSelectField{ id } } } }"""
    opts = json.dumps([{"name": n, "color": c, "description": d} for n, c, d in wanted])
    payload = json.dumps({"query": q, "variables": {"id": field_id, "opts": json.loads(opts)}})
    r = subprocess.run(["gh", "api", "graphql", "--input", "-"], input=payload, capture_output=True, text=True)
    return r.returncode == 0 and "errors" not in r.stdout


def board(args, repo, owner):
    wanted = COLUMNS + ([QUARANTINE] if args.visibility == "public" else [])
    names = [n for n, _, _ in wanted]
    created = False
    if args.board == "new":
        p = gh_json("project", "create", "--owner", owner, "--title", args.title or f"{repo['name']} · esteira",
                    "--format", "json")
        number, created = p["number"], True
    else:
        number = int(args.board)
    proj = gh_json("project", "view", str(number), "--owner", owner, "--format", "json")
    run("gh", "project", "link", str(number), "--owner", owner, "--repo", repo["nameWithOwner"], check=False)
    fs = {f["name"]: f for f in fields(number, owner)}
    status = fs.get("Status")
    field_name = "Status"
    have_all = status and set(names) <= {o["name"] for o in status.get("options", [])}
    if not have_all:
        # Board novo: troca as opções do Status (não há itens). Board existente: nunca apaga as
        # colunas de ninguém; cria um campo próprio, "Esteira", e o board passa a usar esse.
        if not (created and status and set_options(status["id"], wanted)):
            field_name = "Esteira"
            if field_name not in fs:
                run("gh", "project", "field-create", str(number), "--owner", owner, "--name", field_name,
                    "--data-type", "SINGLE_SELECT", "--single-select-options", ",".join(names))
    f = {x["name"]: x for x in fields(number, owner)}[field_name]
    options = {o["name"]: o["id"] for o in f.get("options", [])}
    missing = [n for n in names if n not in options]
    if missing:
        out({"erro": f"o campo {field_name} do board {number} não tem as colunas {missing}; "
                     "acrescente-as na interface do GitHub e rode configure de novo"}, 1)
    return {"project_number": number, "project_id": proj["id"], "project_url": proj.get("url"),
            "status_field_name": field_name, "status_field_id": f["id"],
            "status_options": {n: options[n] for n in names}, "board_created": created}


def labels(repo, public):
    existing = {l["name"] for l in gh_json("label", "list", "--repo", repo, "--limit", "200", "--json", "name")}
    wanted = dict(LABELS)
    if public:
        wanted["future"] = ("ededed", "Idea kept for the future")
    made = []
    for name, (color, desc) in wanted.items():
        if name not in existing:
            run("gh", "label", "create", name, "--repo", repo, "--color", color, "--description", desc)
            made.append(name)
    return made


def evidence(args, repo, visibility):
    if args.evidence_repo == "none":
        return None, False
    name = args.evidence_repo or f"{repo['nameWithOwner']}-evidence"
    if run("gh", "repo", "view", name, check=False).returncode == 0:
        return name, False
    run("gh", "repo", "create", name, f"--{visibility}", "--add-readme",
        "--description", f"QA and design evidence for {repo['nameWithOwner']} (generated by the pipeline)")
    return name, True


def configure(args):
    repo = repo_info()
    owner = repo["owner"]["login"]
    root = git_root() or TARGET
    sub = str(TARGET.relative_to(root)) if TARGET != root else ""
    slug = re.sub(r"[^a-z0-9-]+", "-", (repo["nameWithOwner"] + ("-" + sub if sub else "")).lower().replace("/", "-"))
    b = board(args, repo, owner)
    made_labels = labels(repo["nameWithOwner"], args.visibility == "public")
    ev, ev_created = evidence(args, repo, repo["visibility"].lower())
    me = run("gh", "api", "user", "--jq", ".login").stdout.strip()
    maintainers = [m for m in (args.maintainers or me).split(",") if m]
    cfg_path = DEST / "config.json"
    old = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    tpl = json.loads((PIPELINE / "config.template.json").read_text())
    cfg = {**tpl, **{k: v for k, v in old.items() if k in ("stages", "loops", "timeouts", "max_workers",
                                                            "min_free_ram_gb", "trusted_domains", "claude_command",
                                                            "git_ssh_command", "monitor_spaces", "manual_spaces")}}
    cfg.update({
        "repo": repo["nameWithOwner"], "owner": owner, "owner_type": owner_type(owner),
        "visibility": args.visibility, "monitors": args.visibility == "public",
        "base_branch": args.base or repo["defaultBranchRef"]["name"],
        "language": args.language, "merge_on_qa": args.merge_on_qa == "yes",
        "maintainers": maintainers, "bot_account": me,
        "project_number": b["project_number"], "project_id": b["project_id"],
        "status_field_name": b["status_field_name"], "status_field_id": b["status_field_id"],
        "status_options": b["status_options"],
        "quarantine": {"label": "future", "status": QUARANTINE[0]} if args.visibility == "public" else None,
        "evidence_repo": ev,
        "evidence_checkout": f"~/.local/share/esteira/{slug}/evidence",
        "worktrees_dir": str(root.parent / f"{root.name}-wt"),
        "subdir": str(TARGET.relative_to(root)) if TARGET != root else "",
        "state_dir": f"~/.local/state/esteira/{slug}",
    })
    DEST.mkdir(parents=True, exist_ok=True)
    tmp = cfg_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, cfg_path)
    out({"config": str(cfg_path.relative_to(TARGET)), "board": b, "labels_criadas": made_labels,
         "repositorio_de_evidencias": ev, "evidencias_criado": ev_created, "mantenedores": maintainers,
         "monitores": cfg["monitors"]})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("projects")
    sub.add_parser("install")
    c = sub.add_parser("configure")
    c.add_argument("--board", required=True, help="new ou o número de um projeto existente")
    c.add_argument("--title")
    c.add_argument("--visibility", required=True, choices=["public", "private"])
    c.add_argument("--merge-on-qa", required=True, choices=["yes", "no"])
    c.add_argument("--language", required=True, choices=["en", "pt-BR"])
    c.add_argument("--base")
    c.add_argument("--maintainers")
    c.add_argument("--evidence-repo")
    a = ap.parse_args()
    {"check": check, "projects": projects}.get(a.cmd, lambda: None)() if a.cmd in ("check", "projects") else None
    if a.cmd == "install":
        install()
    if a.cmd == "configure":
        configure(a)


if __name__ == "__main__":
    main()
