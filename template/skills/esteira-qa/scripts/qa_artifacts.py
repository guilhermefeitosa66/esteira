#!/usr/bin/env python3
"""Artefatos locais do QA BOT. Python 3.10+, somente biblioteca padrão.

Não executa alvos, publica em boards ou comprova a veracidade de registros.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
import sys
import uuid

VERSION = "1.0"
STATES = {"PASSOU", "FALHOU", "BLOQUEADO", "NAO_EXECUTADO", "NAO_APLICAVEL"}
BUG_STATES = {"ABERTO", "REABERTO", "EM_RETESTE", "CORRIGIDO_VERIFICADO"}
UI_PLATFORMS = {"web", "web-mobile", "android", "ios", "desktop"}
PLATFORMS = UI_PLATFORMS | {"api", "database", "document"}
KINDS = {"screenshot", "technical", "download", "recording"}
VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}
# MP4/MOV trazem "ftyp" no começo; Matroska e WebM, o cabeçalho EBML.
VIDEO_MAGIC = (b"ftyp", b"\x1a\x45\xdf\xa3")
ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
RESERVED = {'con', 'prn', 'aux', 'nul'} | {f'{prefix}{i}' for prefix in ('com', 'lpt') for i in range(1, 10)}
LABELS = {'PASSOU': 'Passou', 'FALHOU': 'Falhou', 'BLOQUEADO': 'Bloqueado',
          'NAO_EXECUTADO': 'Não executado', 'NAO_APLICAVEL': 'Não aplicável',
          'ABERTO': 'Aberto', 'REABERTO': 'Reaberto', 'EM_RETESTE': 'Em reteste',
          'CORRIGIDO_VERIFICADO': 'Corrigido e verificado'}
CONTEXT_LABELS = {'environment': 'Ambiente', 'build': 'Build', 'platform': 'Plataforma',
                  'persona': 'Persona', 'tenant': 'Empresa/tenant'}


def display_context(context):
    return ' · '.join(f'{CONTEXT_LABELS.get(key, key)}: {value}' for key, value in context.items())


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    """Troca atômica; chamador mantém lock nas mutações de rodada existente."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".qa-", suffix=".tmp", delete=False) as stream:
        tmp = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def valid_id(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None and value.casefold() not in RESERVED


def inside(root, relative):
    """Evidências usam caminhos relativos portáteis, sem fuga ou symlink."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("caminho deve ser relativo com barras /, sem drive ou URL")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("caminho fora da rodada")
    root = Path(root).resolve()
    current = root
    for piece in part.parts:
        current = current / piece
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("link de filesystem não é evidência portátil")
    target = current.resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("caminho fora da rodada")
    return target


@contextmanager
def locked(root):
    path = Path(root) / ".qa.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("rodada ocupada; verificar escritor ativo antes de remover lock abandonado")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "at": now()}))
        yield
    finally:
        path.unlink(missing_ok=True)


def required_text(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except (ValueError, TypeError, AttributeError):
        return False


def moment(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def context_for(run, scenario):
    return {**run.get("context", {}), **scenario.get("context", {})}


def validate(run, root):
    """Verifica integridade e coerência, nunca qualidade semântica/visual por si só."""
    errors, warnings = [], []
    if not isinstance(run, dict):
        return {"valid": False, "errors": ["run deve ser objeto"], "warnings": []}
    if run.get("schema_version") != VERSION:
        errors.append("schema_version não suportada")
    if not valid_id(run.get("id")):
        errors.append("id de rodada inválido")
    for field in ("project", "executor", "created_at"):
        if not required_text(run.get(field)):
            errors.append(f"rodada sem {field}")
    if not timestamp(run.get("created_at")):
        errors.append("created_at requer timestamp ISO com fuso")
    if not isinstance(run.get("context"), dict):
        errors.append("context deve ser objeto")
        return {"valid": False, "errors": errors, "warnings": warnings}

    indexes = {}
    for collection in ("sources", "requirements", "evidence", "scenarios", "bugs", "effects"):
        rows = run.get(collection)
        if not isinstance(rows, list):
            errors.append(f"{collection} deve ser lista")
            rows = []
        idx, normalized = {}, set()
        for row in rows:
            if not isinstance(row, dict) or not valid_id(row.get("id")):
                errors.append(f"{collection}: item/ID inválido")
                continue
            folded = row["id"].casefold()
            if folded in normalized:
                errors.append(f"{collection}: ID duplicado/colisão de caixa {row['id']}")
            normalized.add(folded)
            idx[row["id"]] = row
        indexes[collection] = idx

    sources, rules, evidence, scenarios, bugs, effects = (
        indexes[k] for k in ("sources", "requirements", "evidence", "scenarios", "bugs", "effects")
    )
    def needs_text(obj, fields, label):
        for key in fields:
            if not required_text(obj.get(key)):
                errors.append(f"{label}: falta {key}")

    def links(obj, field, index, label, required=False):
        refs = obj.get(field, [])
        if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
            errors.append(f"{label}: {field} deve ser lista de IDs")
            return []
        if required and not refs:
            errors.append(f"{label}: sem {field}")
        for ref in refs:
            if ref not in index:
                errors.append(f"{label}: {field} desconhecido {ref}")
        return refs

    for source in sources.values():
        needs_text(source, ("location", "version"), source["id"])
    for rule in rules.values():
        needs_text(rule, ("text", "locator"), rule["id"])
        if rule.get("source") not in sources:
            errors.append(f"{rule['id']}: fonte desconhecida")
        if rule.get("scope", "in") not in {"in", "out"}:
            errors.append(f"{rule['id']}: scope inválido")
        if rule.get("scope") == "out":
            needs_text(rule, ("reason",), rule["id"])

    hashes = {}
    for ev in evidence.values():
        label = ev["id"]
        needs_text(ev, ("caption", "tool", "captured_at"), label)
        if not timestamp(ev.get("captured_at")):
            errors.append(f"{label}: captured_at requer fuso")
        if ev.get("kind") not in KINDS:
            errors.append(f"{label}: tipo de evidência inválido")
        if ev.get("reviewed") is not True or not required_text(ev.get("review_note")):
            errors.append(f"{label}: prova ainda não revisada para distribuição")
        try:
            path = inside(root, ev.get("path"))
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError("arquivo ausente ou vazio")
            actual = digest(path)
            if actual != ev.get("sha256"):
                errors.append(f"{label}: hash divergente")
            if actual in hashes:
                warnings.append(f"{label}: conteúdo idêntico a {hashes[actual]}; conferir reuso declarado")
            hashes[actual] = label
            if ev.get("kind") == "screenshot":
                with path.open("rb") as stream:
                    signature = stream.read(12)
                png = signature.startswith(b"\x89PNG\r\n\x1a\n") and path.suffix.lower() == ".png"
                jpg = signature.startswith(b"\xff\xd8\xff") and path.suffix.lower() in {".jpg", ".jpeg"}
                if not (png or jpg):
                    errors.append(f"{label}: screenshot precisa ser PNG/JPEG real")
            if ev.get("kind") == "recording":
                with path.open("rb") as stream:
                    signature = stream.read(16)
                # A extensão é o que faz o relatório e o navegador escolherem o decodificador;
                # a assinatura é o que impede registrar outra coisa como gravação.
                if path.suffix.lower() not in VIDEO_SUFFIXES:
                    errors.append(f"{label}: gravação precisa de extensão de vídeo "
                                  f"({', '.join(sorted(VIDEO_SUFFIXES))})")
                elif not any(mark in signature for mark in VIDEO_MAGIC):
                    errors.append(f"{label}: gravação precisa ser MP4/Matroska real")
        except (ValueError, OSError) as exc:
            errors.append(f"{label}: {exc}")

    mapped = set()
    for scenario in scenarios.values():
        label = scenario["id"]
        needs_text(scenario, ("title", "objective"), label)
        refs = links(scenario, "rules", rules, label, required=True)
        mapped.update(refs)
        linked_bugs = links(scenario, "bugs", bugs, label)
        state = scenario.get("status")
        if state not in STATES:
            errors.append(f"{label}: status inválido")
        if state in {"BLOQUEADO", "NAO_APLICAVEL"}:
            needs_text(scenario, ("reason",), label)
        if state == "NAO_APLICAVEL":
            needs_text(scenario, ("decision",), label)
        if not isinstance(scenario.get("context", {}), dict):
            errors.append(f"{label}: context inválido")
            continue
        ctx = context_for(run, scenario)
        if state in {"PASSOU", "FALHOU"}:
            needs_text(ctx, ("environment", "build", "platform", "persona", "tenant"), label)
            if ctx.get("platform") not in PLATFORMS:
                errors.append(f"{label}: plataforma desconhecida")
            if not scenario.get("gherkin") or not scenario.get("preconditions"):
                errors.append(f"{label}: execução conclusiva sem BDD/pré-condições")
        steps = scenario.get("steps")
        if not isinstance(steps, list):
            errors.append(f"{label}: steps deve ser lista")
            continue
        statuses, step_ids = [], set()
        for step in steps:
            if not isinstance(step, dict) or not valid_id(step.get("id")):
                errors.append(f"{label}: passo inválido")
                continue
            slabel = f"{label}/{step['id']}"
            if step["id"].casefold() in step_ids:
                errors.append(f"{slabel}: passo duplicado")
            step_ids.add(step["id"].casefold())
            status = step.get("status")
            statuses.append(status)
            if status not in STATES:
                errors.append(f"{slabel}: status inválido")
            needs_text(step, ("action", "expected"), slabel)
            evrefs = links(step, "evidence", evidence, slabel,
                           required=status in {"PASSOU", "FALHOU"})
            if status in {"PASSOU", "FALHOU"}:
                needs_text(step, ("actual",), slabel)
                if ctx.get("platform") in UI_PLATFORMS and not any(
                    evidence.get(ref, {}).get("kind") == "screenshot" for ref in evrefs
                ):
                    errors.append(f"{slabel}: verificação UI sem captura")
            if status in {"BLOQUEADO", "NAO_APLICAVEL"}:
                needs_text(step, ("reason",), slabel)
        if "FALHOU" in statuses and state != "FALHOU":
            errors.append(f"{label}: falha comprovada exige FALHOU no CT")
        if state == "FALHOU" and "FALHOU" not in statuses:
            errors.append(f"{label}: FALHOU sem passo que comprove falha")
        if state == "PASSOU":
            if not statuses or "PASSOU" not in statuses or any(x not in {"PASSOU", "NAO_APLICAVEL"} for x in statuses):
                errors.append(f"{label}: PASSOU com passos incompletos")
            if any(bugs.get(ref, {}).get("status") != "CORRIGIDO_VERIFICADO" for ref in linked_bugs):
                errors.append(f"{label}: PASSOU com bug impeditivo aberto")
        if state == "FALHOU" and not any(
            bugs.get(ref, {}).get("status") in BUG_STATES - {"CORRIGIDO_VERIFICADO"}
            for ref in linked_bugs
        ):
            errors.append(f"{label}: falha sem bug aberto vinculado")
        if state == "NAO_EXECUTADO" and any(s in {"PASSOU", "FALHOU"} for s in statuses):
            warnings.append(f"{label}: houve passos executados, CT ainda inconclusivo")

    for bug in bugs.values():
        label = bug["id"]
        needs_text(bug, ("title", "expected", "observed", "impact", "severity", "frequency"), label)
        original_context = bug.get('context')
        if not isinstance(original_context, dict):
            errors.append(f"{label}: falta context da falha original")
            original_context = {}
        else:
            needs_text(original_context, ('environment', 'build', 'platform', 'persona', 'tenant'), label)
        if bug.get("status") not in BUG_STATES:
            errors.append(f"{label}: estado de bug inválido")
        if bug.get("scenario") not in scenarios:
            errors.append(f"{label}: cenário original desconhecido")
        elif label not in scenarios[bug["scenario"]].get("bugs", []):
            errors.append(f"{label}: vínculo com CT precisa ser bidirecional")
        if not isinstance(bug.get("steps"), list) or not bug["steps"] or any(not required_text(s) for s in bug["steps"]):
            errors.append(f"{label}: reprodução precisa de passos textuais")
        original = links(bug, "evidence", evidence, label, required=True)
        if 'retest' in bug:
            attempt = bug['retest']
            if not isinstance(attempt, dict):
                errors.append(f"{label}: retest deve ser objeto")
                continue
            attempt_status = attempt.get('status')
            if attempt_status not in {'PASSOU', 'FALHOU', 'BLOQUEADO', 'NAO_EXECUTADO'}:
                errors.append(f"{label}: estado de reteste inválido")
            links(attempt, 'evidence', evidence, label + '/retest',
                  required=attempt_status in {'PASSOU', 'FALHOU'})
            if attempt_status in {'BLOQUEADO', 'NAO_EXECUTADO'}:
                needs_text(attempt, ('reason',), label + '/retest')
            else:
                needs_text(attempt, ('at', 'build', 'scenario', 'conclusion'), label + '/retest')
                if attempt.get('scenario') != bug.get('scenario'):
                    errors.append(f"{label}: reteste deve comprovar o próprio CT do bug")
            if 'at' in attempt and not timestamp(attempt['at']):
                errors.append(f"{label}: data de reteste sem fuso")
        if bug.get("status") == "CORRIGIDO_VERIFICADO":
            rt = bug.get("retest", {})
            if not isinstance(rt, dict):
                errors.append(f"{label}: retest inválido")
                continue
            needs_text(rt, ("build", "at", "scenario", "conclusion"), label)
            if not timestamp(rt.get("at")):
                errors.append(f"{label}: data de reteste sem fuso")
            fresh = links(rt, "evidence", evidence, label + "/retest", required=True)
            tested = scenarios.get(rt.get("scenario"), {})
            if rt.get('scenario') != bug.get('scenario'):
                errors.append(f"{label}: reteste deve comprovar o próprio CT do bug")
            if rt.get("status") != "PASSOU" or tested.get("status") != "PASSOU":
                errors.append(f"{label}: correção sem reteste aprovado")
            fresh_hashes = {evidence.get(ref, {}).get("sha256") for ref in fresh}
            old_hashes = {evidence.get(ref, {}).get("sha256") for ref in original}
            if fresh_hashes & old_hashes:
                errors.append(f"{label}: reteste reutiliza prova original")
            tested_refs = {ref for step in tested.get("steps", []) for ref in step.get("evidence", [])}
            if not set(fresh).issubset(tested_refs):
                errors.append(f"{label}: prova de reteste não pertence ao CT aprovado")
            if tested and rt.get("build") != context_for(run, tested).get("build"):
                errors.append(f"{label}: build de reteste diverge do CT")
            if tested:
                tested_context = context_for(run, tested)
                for key in ('persona', 'tenant', 'platform'):
                    if original_context.get(key) != tested_context.get(key):
                        errors.append(f"{label}: reteste diverge da falha original em {key}")
            dates = [evidence.get(ref, {}).get("captured_at") for ref in original + fresh]
            if fresh and original and all(timestamp(value) for value in dates) and timestamp(rt.get("at")):
                old_end = max(moment(evidence[ref]["captured_at"]) for ref in original if ref in evidence)
                new_start = min(moment(evidence[ref]["captured_at"]) for ref in fresh if ref in evidence)
                new_end = max(moment(evidence[ref]["captured_at"]) for ref in fresh if ref in evidence)
                if new_start < old_end or moment(rt["at"]) < new_end:
                    errors.append(f"{label}: cronologia de reteste inconsistente")

    for rule_id, rule in rules.items():
        if rule.get("scope", "in") == "in" and rule_id not in mapped:
            warnings.append(f"{rule_id}: regra em escopo sem cenário")
    for effect in effects.values():
        needs_text(effect, ("action", "state"), effect["id"])
        if effect.get("state") == "uncertain":
            warnings.append(f"{effect['id']}: efeito incerto; reconciliar antes de repetir")
    if not scenarios:
        warnings.append("rodada sem cenários: sem base de execução")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def metrics(run):
    counts = Counter(s["status"] for s in run.get("scenarios", []))
    total = sum(counts.values())
    conclusive = counts["PASSOU"] + counts["FALHOU"]
    applicable = total - counts["NAO_APLICAVEL"]
    return {"total": total, "counts": {s: counts[s] for s in sorted(STATES)},
            "conclusive": conclusive, "applicable": applicable,
            "approval_rate": counts["PASSOU"] / conclusive if conclusive else None,
            "execution_rate": conclusive / applicable if applicable else None}


CSS = """
@page {size:A4;margin:16mm 15mm} *{box-sizing:border-box}
body{font:14px/1.6 'Segoe UI',Arial,sans-serif;color:#233443;background:#fff;margin:0}
main{max-width:1080px;margin:auto;padding:32px} .eyebrow{font-size:11px;letter-spacing:1.5px;color:#526779}
h1{font-size:30px;line-height:1.2;color:#12354c;margin:12px 0 18px;border-bottom:4px solid #de733d;padding-bottom:16px}
h2{font-size:20px;color:#12354c;margin-top:28px;break-after:avoid} h3{font-size:16px;break-after:avoid}
a{color:#155c80} .meta,.notice{background:#edf3f6;padding:14px;border-left:4px solid #155c80;margin:16px 0}
.notice{background:#fff3de;border-color:#a76608} .metrics{display:flex;gap:16px;flex-wrap:wrap}
.metric{border-top:3px solid #155c80;padding:12px 16px;background:#edf3f6;min-width:170px}
.metric strong{display:block;font-size:30px;color:#12354c} table{border-collapse:collapse;width:100%;font-size:12px}
th,td{border:1px solid #c8d5df;padding:8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#eaf1f6} .badge{font-size:12px;font-weight:700;padding:4px 9px;display:inline-block;background:#e8edf0}
.PASSOU{background:#e0f2e6;color:#176735}.FALHOU{background:#fde7e7;color:#982b2b}
.BLOQUEADO{background:#fff0ce;color:#815006}pre{white-space:pre-wrap;overflow-wrap:anywhere;break-inside:avoid;background:#102b3e;color:#eaf4fa;padding:16px;font-size:12px}
.step{border:1px solid #c8d5df;margin:22px 0;padding:16px;break-inside:avoid}
figure{margin:16px 0;break-inside:avoid}figure img,figure video{max-width:100%;max-height:180mm;object-fit:contain;display:block;margin:auto}
figcaption{font-size:12px;color:#435c6c;margin-top:8px}.technical{font-size:11px;max-height:none}
.small{font-size:11px;color:#526779;overflow-wrap:anywhere}footer{border-top:1px solid #c8d5df;margin-top:30px;padding-top:12px;font-size:11px;color:#526779}
@media print{main{max-width:none;padding:0}body{font-size:11pt}h1{font-size:23pt}h2{font-size:16pt}
.step{break-before:page;border:none;padding:0} a{color:inherit;text-decoration:none}.metric{min-width:120px}thead{display:table-header-group}
figure video{display:none}
footer{display:none}}
"""


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def md(value):
    return esc(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def badge(state):
    return f'<span class="badge {esc(state)}">{esc(LABELS.get(state, state))}</span>'


def page(run, title, body):
    demo = '<div class="notice">DEMONSTRAÇÃO LOCAL — não é teste de sistema de cliente.</div>' if run.get("demonstration") else ""
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head><body><main>'
            f'<div class="eyebrow">{esc(run.get("consultancy") or "QA BOT")} · QUALIDADE DE SOFTWARE</div>'
            f'<h1>{esc(title)}</h1>{demo}<div class="meta">Projeto: {esc(run["project"])} · '
            f'Cliente: {esc(run.get("client") or "não informado")}<br>Rodada: {esc(run["id"])} · '
            f'Executor técnico: {esc(run["executor"])}<br>Autoria: {esc(run.get("author") or "não informada")}</div>'
            f'{body}<footer>QA BOT · Rodada {esc(run["id"])} · Documento gerado em {esc(now())}'
            '</footer></main></body></html>')


def figures(run, refs, root, relative_prefix):
    index = {e["id"]: e for e in run["evidence"]}
    body, markdown = [], []
    for ref in refs:
        ev = index[ref]
        source = inside(root, ev["path"])
        ext = source.suffix.lower()
        link = f'{relative_prefix}evidence/{ref}{ext}'
        label = f'{ref} — {ev["caption"]}'
        if ev["kind"] == "screenshot":
            mime = "image/png" if ext == ".png" else "image/jpeg"
            payload = base64.b64encode(source.read_bytes()).decode("ascii")
            body.append(f'<figure><img src="data:{mime};base64,{payload}" alt="{esc(label)}">'
                        f'<figcaption>{esc(label)}</figcaption></figure>')
            markdown.append(f'![{md(label)}]({link})')
        elif ev["kind"] == "recording":
            # Gravação fica como arquivo ao lado, nunca embutida: base64 de vídeo estoura o HTML e
            # o PDF. Consequência declarada: o .html depende do irmão em evidence/ para tocar.
            body.append(f'<figure><video controls preload="metadata" playsinline src="{esc(link)}">'
                        f'</video><figcaption>{esc(label)} — '
                        f'<a href="{esc(link)}">{esc(ref + ext)}</a></figcaption></figure>')
            markdown.append(f'[{md(label)}]({link}) — {md(ev["kind"])}')
        else:
            body.append(f'<h3>{esc(label)}</h3><p>Artefato técnico real: '
                        f'<a href="{esc(link)}">{esc(ref + ext)}</a></p>')
            if ev["kind"] == "technical" and ext in {".txt", ".json", ".jsonl", ".csv", ".log"}:
                # Leitura tardia: só o extrato técnico precisa do conteúdo em memória.
                content = source.read_bytes()
                excerpt = content.decode("utf-8", errors="replace")[:6000]
                body.append(f'<pre class="technical">{esc(excerpt)}</pre>')
                if len(content) > 6000:
                    body.append('<p class="small">Extrato limitado; consultar arquivo completo.</p>')
            markdown.append(f'[{md(label)}]({link}) — {md(ev["kind"])}')
        provenance = f'{ev["captured_at"]} · {ev["tool"]} · SHA-256 {ev["sha256"]}'
        body.append(f'<p class="small">{esc(provenance)}</p>')
        markdown.append(provenance)
    return "\n".join(body), "\n\n".join(markdown)


def write_pair(out, stem, run, title, body, markdown):
    path = out / stem
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".html").write_text(page(run, title, body), encoding="utf-8")
    header = (f'# {md(title)}\n\nProjeto: {md(run["project"])} · Run: {run["id"]} · '
              f'Executor técnico: {md(run["executor"])}\n\nCliente: {md(run.get("client") or "não informado")} · '
              f'Consultoria: {md(run.get("consultancy") or "não informada")} · '
              f'Autoria: {md(run.get("author") or "não informada")}\n\n')
    if run.get("demonstration"):
        header += '> DEMONSTRAÇÃO LOCAL — não é teste de sistema de cliente.\n\n'
    path.with_suffix(".md").write_text(header + markdown + "\n", encoding="utf-8")


def traceability(run, rule_ids):
    sources = {s["id"]: s for s in run["sources"]}
    paragraphs, markdown = [], []
    for rule in run["requirements"]:
        if rule["id"] in rule_ids:
            source = sources[rule["source"]]
            text = (f'{rule["id"]}: {rule["text"]} Fonte: {source["location"]}, '
                    f'versão {source["version"]}, {rule["locator"]}.')
            paragraphs.append(f'<p>{esc(text)}</p>')
            markdown.append(md(text))
    return ''.join(paragraphs), '\n\n'.join(markdown)


def report(run, root, snapshot):
    check = validate(run, root)
    if not check["valid"]:
        raise ValueError("artefatos inválidos: " + "; ".join(check["errors"]))
    if not valid_id(snapshot):
        raise ValueError("snapshot inválido")
    destination = inside(root, f"delivery/{snapshot}")
    if destination.exists():
        raise FileExistsError('snapshot já existe; use novo identificador')
    # Só promover para o nome final depois de gerar todo o pacote. Uma interrupção
    # deixa staging identificável e permite repetir com o mesmo snapshot final.
    out = inside(root, f"delivery/.building-{snapshot}-{uuid.uuid4().hex}")
    out.mkdir(parents=True, exist_ok=False)
    (out / "evidence").mkdir()
    for ev in run["evidence"]:
        source = inside(root, ev["path"])
        # Copiar apenas evidências declaradas e revisadas, nunca pasta inteira.
        (out / "evidence" / (ev["id"] + source.suffix.lower())).write_bytes(source.read_bytes())
    write_json(out / "run-snapshot.json", run)
    score = metrics(run)
    table = '<table><thead><tr><th>Estado</th><th>CTs</th></tr></thead><tbody>'
    mtable = '| Estado | CTs |\n|---|---:|\n'
    for state, count in score["counts"].items():
        table += f'<tr><td>{badge(state)}</td><td>{count}</td></tr>'
        mtable += f'| {LABELS.get(state, state)} | {count} |\n'
    table += '</tbody></table>'
    approval = 'sem base' if score["approval_rate"] is None else f'{score["approval_rate"]:.1%}'.replace('.', ',')
    coverage = 'sem base' if score["execution_rate"] is None else f'{score["execution_rate"]:.1%}'.replace('.', ',')
    narrative = run.get("summary") or "Síntese gerencial não informada; avaliar resultados e pendências abaixo."
    counts = (f'Aprovação: {score["counts"]["PASSOU"]}/{score["conclusive"]} conclusivos ({approval}). '
              f'Execução: {score["conclusive"]}/{score["applicable"]} aplicáveis ({coverage}).')
    overview = f'<p>{esc(narrative)}</p><div class="metrics">'
    for label, number in (("Planejados", score["total"]), ("Conclusivos", score["conclusive"]),
                          ("Bloqueados", score["counts"]["BLOQUEADO"]), ("Bugs", len(run["bugs"]))):
        overview += f'<div class="metric"><strong>{number}</strong>{label}</div>'
    overview += f'</div><p>{esc(counts)}</p>{table}'
    details, detailmd = [], []
    plan, planmd = [], []
    for scenario in run["scenarios"]:
        sid, title = scenario["id"], scenario["title"]
        ctx = context_for(run, scenario)
        context = display_context(ctx)
        rules = ', '.join(scenario["rules"])
        body = (f'<p>{badge(scenario["status"])}</p><p>{esc(scenario["objective"])}</p>'
                f'<div class="meta">{esc(context)}<br>Regras: {esc(rules)}<br>'
                f'Pré-condições: {esc(scenario.get("preconditions", "não informadas"))}</div>')
        smd = f'{LABELS[scenario["status"]]}\n\n{md(scenario["objective"])}\n\n{md(context)}\n\nRegras: {rules}\n\n'
        source_html, source_md = traceability(run, scenario["rules"])
        body += source_html
        smd += source_md + '\n\nPré-condições: ' + md(scenario.get('preconditions', 'não informadas')) + '\n\n'
        gherkin = scenario.get("gherkin", [])
        gherkin = '\n'.join(gherkin) if isinstance(gherkin, list) else str(gherkin)
        body += f'<h2>Cenário BDD</h2><pre>{esc(gherkin)}</pre>'
        smd += f'```gherkin\n{gherkin}\n```\n\n'
        reason = scenario.get("reason") or scenario.get("conclusion") or LABELS[scenario["status"]]
        body += f'<h2>Conclusão e alcance</h2><p>{esc(reason)}</p>'
        smd += f'## Conclusão e alcance\n\n{md(reason)}\n\n'
        if scenario.get("bugs"):
            body += '<p>Bugs: ' + ', '.join(f'<a href="../bugs/{esc(b)}.html">{esc(b)}</a>' for b in scenario["bugs"]) + '</p>'
            smd += 'Bugs: ' + ', '.join(f'[{b}](../bugs/{b}.md)' for b in scenario["bugs"]) + '\n'
        for step in scenario["steps"]:
            body += f'<section class="step"><h2>{esc(step["id"])} — {esc(step["action"])}</h2>{badge(step["status"])}'
            smd += f'## {md(step["id"])} — {md(step["action"])}\n\n{LABELS[step["status"]]}\n\n'
            for key, label in (("expected", "Esperado"), ("actual", "Observado"), ("reason", "Limite/impedimento")):
                if step.get(key):
                    body += f'<p><b>{label}:</b> {esc(step[key])}</p>'
                    smd += f'**{label}:** {md(step[key])}\n\n'
            fhtml, fmd = figures(run, step.get("evidence", []), root, "../")
            body += fhtml + '</section>'
            smd += fmd + '\n\n'
        write_pair(out, f'cases/{sid}', run, sid + ' — ' + title, body, smd)
        details.append(f'<tr><td><a href="cases/{esc(sid)}.html">{esc(sid)}</a></td><td>{esc(title)}</td><td>{esc(rules)}</td><td>{badge(scenario["status"])}</td></tr>')
        detailmd.append(f'| [{sid}](cases/{sid}.md) | {md(title)} | {rules} | {LABELS[scenario["status"]]} |')
        plan.append(f'<h2>{esc(sid)} — {esc(title)}</h2><p>{esc(scenario["objective"])}</p><pre>{esc(gherkin)}</pre>')
        planmd.append(f'## {sid} — {md(title)}\n\n{md(scenario["objective"])}\n\n```gherkin\n{gherkin}\n```')
    detail_table = '<table><thead><tr><th>CT</th><th>Objetivo</th><th>Regras</th><th>Resultado</th></tr></thead><tbody>' + ''.join(details) + '</tbody></table>'
    detail_markdown = '| CT | Objetivo | Regras | Resultado |\n|---|---|---|---|\n' + '\n'.join(detailmd)
    rulehtml, rulemd = '<h2>Rastreabilidade por regra</h2>', '\n\n## Rastreabilidade por regra\n\n'
    for rule in run["requirements"]:
        mapped = [s for s in run["scenarios"] if rule["id"] in s["rules"]]
        proved = bool(mapped) and all(s["status"] == "PASSOU" for s in mapped)
        state = "FORA DO ESCOPO" if rule.get("scope") == "out" else "COMPROVADA" if proved else "NÃO COMPROVADA"
        explanation = f'{rule["id"]}: {rule["text"]} — {state}. Fonte {rule["source"]}, {rule["locator"]}.'
        rulehtml += f'<p>{esc(explanation)}</p>'
        rulemd += md(explanation) + '\n\n'
    for source in run["sources"]:
        citation = f'{source["id"]}: {source["location"]} · versão {source["version"]}'
        rulehtml += f'<p class="small">{esc(citation)}</p>'
        rulemd += md(citation) + '\n\n'
    bughtml, bugmd = '<h2>Defeitos e impacto</h2>', '\n\n## Defeitos e impacto\n\n'
    for bug in run["bugs"]:
        bid = bug["id"]
        body = f'<p>{esc(LABELS[bug["status"]])} · {esc(bug["severity"])}</p>'
        bmd = f'{LABELS[bug["status"]]} · {md(bug["severity"])}\n\n'
        original_ct = next(s for s in run["scenarios"] if s["id"] == bug["scenario"])
        trace = f'CT {bug["scenario"]} · Regras {", ".join(original_ct["rules"])}'
        bug_context = bug.get('context') or context_for(run, original_ct)
        context_text = display_context(bug_context)
        body += f'<p>{esc(trace)}</p><div class="meta">Contexto da falha: {esc(context_text)}</div>'
        bmd += md(trace) + '\n\nContexto da falha: ' + md(context_text) + '\n\n'
        source_html, source_md = traceability(run, original_ct['rules'])
        body += source_html
        bmd += source_md + '\n\n'
        for field, label in (("expected", "Esperado"), ("observed", "Observado"), ("impact", "Impacto"), ("frequency", "Frequência")):
            body += f'<h2>{label}</h2><p>{esc(bug[field])}</p>'
            bmd += f'## {label}\n\n{md(bug[field])}\n\n'
        body += '<h2>Reprodução</h2><ol>' + ''.join(f'<li>{esc(s)}</li>' for s in bug["steps"]) + '</ol>'
        bmd += '## Reprodução\n\n' + '\n'.join(f'{i}. {md(s)}' for i, s in enumerate(bug["steps"], 1)) + '\n\n'
        fhtml, fmd = figures(run, bug["evidence"], root, '../')
        body += fhtml
        bmd += fmd
        if bug.get("retest"):
            rt = bug["retest"]
            rtext = (f'{LABELS.get(rt.get("status"), "Estado não registrado")} · '
                     f'{rt.get("at", "data não registrada")} · build {rt.get("build", "não confirmada")} · '
                     f'{rt.get("conclusion") or rt.get("reason", "conclusão não registrada")}')
            body += f'<h2>Reteste QA</h2><p>{esc(rtext)}</p>'
            bmd += '\n\n## Reteste QA\n\n' + md(rtext) + '\n\n'
            fhtml, fmd = figures(run, rt.get("evidence", []), root, '../')
            body += fhtml
            bmd += fmd
        write_pair(out, f'bugs/{bid}', run, bid + ' — ' + bug["title"], body, bmd)
        bughtml += f'<p><a href="bugs/{esc(bid)}.html">{esc(bid)} — {esc(bug["title"])}</a><br>{esc(bug["severity"])} · {esc(LABELS[bug["status"]])} · {esc(bug["impact"])}</p>'
        bugmd += f'[{bid} — {md(bug["title"])}](bugs/{bid}.md) · {md(LABELS[bug["status"]])} · {md(bug["impact"])}\n\n'
    limits = '<h2>Pendências e dados</h2>'
    limitsmd = '\n\n## Pendências e dados\n\n'
    notes = check["warnings"] + [f'{s["id"]}: {s.get("reason") or LABELS[s["status"]]}' for s in run["scenarios"] if s["status"] not in {"PASSOU", "FALHOU"}]
    notes += [f'{e["id"]}: {e["action"]} — {e["state"]}; {e.get("cleanup", "limpeza não informada")}' for e in run["effects"]]
    for note in notes or ["Nenhuma pendência registrada na base. Conferir alcance da rodada antes de homologar."]:
        limits += f'<p>{esc(note)}</p>'
        limitsmd += md(note) + '\n\n'
    # Gravação que não pertence a um passo é prova da rodada inteira (o vídeo narrado do processo).
    # Sem esta seção ela seria copiada e hasheada, mas nenhum documento a linkaria.
    referenced = {ref for s in run["scenarios"] for step in s["steps"] for ref in step.get("evidence", [])}
    for bug in run["bugs"]:
        referenced.update(bug.get("evidence", []))
        if isinstance(bug.get("retest"), dict):
            referenced.update(bug["retest"].get("evidence", []))
    runwide = [e["id"] for e in run["evidence"] if e["kind"] == "recording" and e["id"] not in referenced]
    runhtml, runmd = '', ''
    if runwide:
        fhtml, fmd = figures(run, runwide, root, '')
        runhtml = '<h2>Gravação da rodada</h2>' + fhtml
        runmd = '\n\n## Gravação da rodada\n\n' + fmd + '\n\n'
    overview += runhtml + bughtml + limits + '<p><a href="detail.html">Abrir detalhamento e provas por CT</a></p>'
    write_pair(out, 'executive', run, 'Relatório executivo', overview,
               md(narrative) + '\n\n' + counts + '\n\n' + mtable + runmd + bugmd + limitsmd)
    write_pair(out, 'detail', run, 'Detalhamento e rastreabilidade', detail_table + rulehtml + limits,
               detail_markdown + rulemd + limitsmd)
    write_pair(out, 'plan', run, 'Plano de testes', ''.join(plan) + rulehtml, '\n\n'.join(planmd) + rulemd)
    files = {p.relative_to(out).as_posix(): digest(p) for p in out.rglob('*') if p.is_file()}
    write_json(out / 'manifest-sha256.json', {"created_at": now(), "files": files,
               "source_run_sha256": digest(Path(root) / 'run.json'), "pdf_review": "pending"})
    if destination.exists():
        raise FileExistsError('snapshot criado concorrentemente; staging preservado')
    # Ambos os destinos foram resolvidos e conferidos dentro da rodada por inside().
    out.rename(destination)
    return {"output": str(destination), "metrics": score, "warnings": check["warnings"],
            "pdf_review": "pending", "files": len(files) + 1}


def init_run(args):
    if not valid_id(args.id):
        raise ValueError("id inválido")
    root = Path(args.path).resolve()
    root.mkdir(parents=True, exist_ok=False)
    run = {"schema_version": VERSION, "id": args.id, "project": args.project,
           "client": args.client, "consultancy": "QA BOT", "author": "",
           "executor": args.executor, "created_at": now(), "demonstration": False,
           "context": {"environment": "", "build": "", "platform": args.platform,
                       "persona": "", "tenant": ""},
           "summary": "", "sources": [], "requirements": [], "scenarios": [],
           "evidence": [], "bugs": [], "effects": []}
    write_json(root / 'run.json', run)
    (root / 'handoff.md').write_text('# Retomar\n\nRodada iniciada. Ler fontes e registrar escopo antes da execução.\n', encoding='utf-8')
    return {"run": str(root / 'run.json'), "status": "NAO_EXECUTADO"}


def register(args, runpath):
    root = runpath.parent
    with locked(root):
        run = read_json(runpath)
        if not valid_id(args.id) or any(e['id'].casefold() == args.id.casefold() for e in run['evidence']):
            raise ValueError('ID de evidência inválido ou já registrado')
        source = inside(root, args.file)
        if not source.is_file() or not source.stat().st_size:
            raise ValueError('arquivo ausente ou vazio')
        if not timestamp(args.at):
            raise ValueError('usar --at ISO 8601 com fuso do momento real da captura')
        ev = {"id": args.id, "path": args.file, "sha256": digest(source), "kind": args.kind,
              "caption": args.caption, "tool": args.tool, "captured_at": args.at,
              "reviewed": args.reviewed, "review_note": args.review_note or ""}
        run['evidence'].append(ev)
        write_json(runpath, run)
    return {"registered": args.id, "reviewed": args.reviewed}


def checkpoint(args, runpath):
    root = runpath.parent
    with locked(root):
        run = read_json(runpath)
        record = {"at": now(), "run": run['id'], "run_sha256": digest(runpath),
                  "note": args.note, "next": args.next}
        with (root / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        write_json(root / 'checkpoint.json', record)
        uncertain = [e for e in run['effects'] if e.get('state') == 'uncertain']
        handoff = (f'# Retomar {run["id"]}\n\nProjeto: {run["project"]}\n\n'
                   f'Checkpoint: {record["at"]}\n\nEstado: {args.note}\n\n'
                   f'Próximo passo: {args.next}\n\nSHA-256 de run.json: {record["run_sha256"]}\n\n'
                   'Revalidar ambiente/build/persona/tenant e reconciliar efeitos antes de repetir escrita.\n\n')
        for effect in uncertain:
            handoff += f'- Efeito incerto {effect["id"]}: {effect["action"]}\n'
        (root / 'handoff.md').write_text(handoff, encoding='utf-8')
    return record


def resume(runpath):
    run = read_json(runpath)
    path = runpath.parent / 'checkpoint.json'
    previous = read_json(path) if path.is_file() else None
    return {"run": run['id'], "project": run['project'], "context": run['context'],
            "metrics": metrics(run), "checkpoint": previous,
            "changed_since_checkpoint": previous is not None and previous['run_sha256'] != digest(runpath),
            "uncertain_effects": [e for e in run['effects'] if e.get('state') == 'uncertain']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='criar rodada vazia; não sobrescreve diretório')
    for name in ('path', 'id', 'project'):
        init.add_argument('--' + name, required=True)
    init.add_argument('--client', default='')
    init.add_argument('--executor', default='QA BOT')
    init.add_argument('--platform', choices=sorted(PLATFORMS), default='web')
    for name in ('validate', 'report', 'evidence', 'checkpoint', 'resume'):
        child = sub.add_parser(name)
        child.add_argument('--run', required=True, help='caminho do run.json')
        if name == 'report':
            child.add_argument('--snapshot', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        if name == 'evidence':
            for field in ('id', 'file', 'caption', 'tool', 'at'):
                child.add_argument('--' + field, required=True)
            child.add_argument('--kind', choices=sorted(KINDS), required=True)
            child.add_argument('--reviewed', action='store_true')
            child.add_argument('--review-note', default='')
        if name == 'checkpoint':
            child.add_argument('--note', required=True)
            child.add_argument('--next', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = init_run(args)
        else:
            path = Path(args.run).resolve()
            if path.name != 'run.json':
                raise ValueError('--run precisa apontar para run.json')
            if args.command == 'evidence':
                result = register(args, path)
            elif args.command == 'checkpoint':
                result = checkpoint(args, path)
            elif args.command == 'resume':
                result = resume(path)
            elif args.command == 'report':
                with locked(path.parent):
                    result = report(read_json(path), path.parent, args.snapshot)
            else:
                result = validate(read_json(path), path.parent)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('valid') is False else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
