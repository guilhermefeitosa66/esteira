#!/usr/bin/env python3
"""Imprime HTML local de QA em PDF usando Chromium/Chrome/Edge disponível."""
import argparse
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


class StandaloneHTML(HTMLParser):
    """Remove links de arquivo da impressão; preserva texto e links web."""
    def __init__(self, base):
        super().__init__(convert_charrefs=False)
        self.base, self.parts = base, []

    def handle_starttag(self, tag, attrs):
        if tag == 'base':
            return
        kept = []
        for key, value in attrs:
            if tag == 'a' and key == 'href' and value and not value.startswith('#'):
                if urlsplit(value).scheme in ('', 'file'):
                    continue
            kept.append(key if value is None else f'{key}="{escape(value, quote=True)}"')
        self.parts.append('<' + tag + (' ' + ' '.join(kept) if kept else '') + '>')
        if tag == 'head':
            self.parts.append('<base href="' + escape(self.base, quote=True) + '">')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag != 'base':
            self.parts.append('</' + tag + '>')

    def handle_data(self, data):
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append('&' + name + ';')

    def handle_charref(self, name):
        self.parts.append('&#' + name + ';')

    def handle_decl(self, decl):
        self.parts.append('<!' + decl + '>')

    def handle_comment(self, data):
        self.parts.append('<!--' + data + '-->')


def standalone_html(source, base):
    parser = StandaloneHTML(base)
    parser.feed(source)
    parser.close()
    return ''.join(parser.parts)


def browser_path(explicit=None):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError('executável de navegador não encontrado')
        return str(path)
    for name in ('chromium', 'chromium-browser', 'google-chrome', 'msedge'):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
        Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    raise ValueError('Chromium/Chrome/Edge não encontrado; informe --browser ou use exportador disponível')


def export(source, destination, browser=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file() or source.suffix.lower() != '.html':
        raise ValueError('entrada precisa ser HTML local existente')
    if destination.exists():
        raise ValueError('PDF existente; use novo nome/snapshot para preservar revisão anterior')
    if destination.suffix.lower() != '.pdf':
        raise ValueError('saída precisa ter extensão .pdf')
    destination.parent.mkdir(parents=True, exist_ok=True)
    executable = browser_path(browser)
    with tempfile.TemporaryDirectory(prefix='qa-bot-browser-') as folder:
        result = Path(folder) / 'output.pdf'
        printable = Path(folder) / 'print.html'
        printable.write_text(standalone_html(source.read_text(encoding='utf-8-sig'),
                             source.parent.as_uri() + '/'), encoding='utf-8')
        cmd = [executable, '--headless', '--no-first-run', '--no-default-browser-check',
               '--disable-background-networking', '--disable-extensions',
               '--no-pdf-header-footer', '--allow-file-access-from-files',
               '--user-data-dir=' + str(Path(folder) / 'profile'),
               '--print-to-pdf=' + str(result), printable.as_uri()]
        process = subprocess.run(cmd, capture_output=True, timeout=55,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if process.returncode or not result.is_file() or result.stat().st_size < 100:
            raise ValueError('navegador não gerou PDF; inspecione execução local e permissões')
        if not result.read_bytes().startswith(b'%PDF-'):
            raise ValueError('saída não é PDF')
        # Escrita exclusiva evita sobrescrever uma entrega criada concorrentemente.
        with destination.open('xb') as stream:
            stream.write(result.read_bytes())
    return {'pdf': str(destination), 'bytes': destination.stat().st_size,
            'review': 'pending: renderizar e inspecionar visualmente',
            'navigation': 'links locais removidos do PDF; navegação portátil nos HTML/MD'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser')
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.input, args.output, args.browser), ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
