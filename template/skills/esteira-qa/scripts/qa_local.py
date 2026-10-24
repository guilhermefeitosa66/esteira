#!/usr/bin/env python3
"""Apoio à execução local do QA BOT. Python 3.10+, somente biblioteca padrão.

Informa portas livres e serve dublês HTTP que o agente declarou, registrando o que recebeu.
Não sobe nem executa o sistema alvo, não descobre integrações e não decide contrato:
chamada que o spec não declara recebe 501 e fica no log.

O log do dublê guarda caminho, query string e corpo como chegaram; só o valor de cabeçalho com nome
sensível vira "<removido>". Usar credenciais de teste e revisar/sanear o log antes de registrá-lo como
evidência. Cabeçalho de contrato removido por conter "key", "token" ou "signature" (Idempotency-Key)
volta ao log quando o spec o lista em "unredacted_headers"; nome com auth, cookie, secret, password,
senha, credential ou session é removido sempre.
"""
from __future__ import annotations

import argparse
import base64
import codecs
from datetime import datetime
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import sys
import threading
import time

BODY_LIMIT = 1024 * 1024
LINE_LIMIT = 65537
REQUEST_LINE_LOG = 2048
DELAY_LIMIT_MS = 600_000
METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}
# 'auth' cobre authorization. As três últimas palavras também aparecem em cabeçalho de contrato
# (Idempotency-Key), por isso só elas podem ser reabertas por unredacted_headers.
ALWAYS_REDACTED = ('auth', 'cookie', 'secret', 'password', 'senha', 'credential', 'session')
SENSITIVE = ALWAYS_REDACTED + ('token', 'key', 'signature')
REDACTED = '<removido>'
BODILESS = {204, 304}
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
SPEC_KEYS = {'name', 'routes', 'unredacted_headers'}
ROUTE_KEYS = {'name', 'method', 'path', 'path_regex', 'delay_ms', 'responses'}
RESPONSE_KEYS = {'status', 'headers', 'json', 'body'}
PORTS_NOTE = ('Porta livre agora não fica reservada: subir o serviço logo em seguida e confirmar que foi ELE '
              '(PID/processo) que ficou escutando nela. Porta publicada por NAT (Docker sem userland-proxy) '
              'não aparece no bind local: informar em --avoid o que docker ps/compose/config mostrarem.')
MOCK_NOTE = ('O log guarda caminho, query string e corpo como chegaram; só valor de cabeçalho com nome sensível vira '
             '<removido>. Usar credenciais de teste e revisar/sanear o log antes de registrá-lo como evidência.')
PARSER_ERRORS = {400: 'linha de requisição inválida', 414: 'linha de requisição acima de 64 KiB',
                 431: 'cabeçalhos em excesso ou linha de cabeçalho longa demais',
                 505: 'versão de HTTP que o dublê não fala'}
TLS_REASON = ('cliente abriu TLS (https) e o dublê só fala HTTP sem TLS: '
              'apontar o alvo para o endereço http do dublê')
H2_REASON = 'cliente falou HTTP/2 sem negociação (h2c/gRPC) e o dublê só fala HTTP/1.1'


def now():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def emit(data, indent=None):
    print(json.dumps(data, ensure_ascii=False, indent=indent), flush=True)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def encodable(text, encoding='utf-8'):
    try:
        text.encode(encoding)
        return True
    except UnicodeEncodeError:
        return False


def required_text(value):
    # Surrogate solto passa no JSON do spec e só quebraria na hora de responder ou de gravar o log.
    return isinstance(value, str) and bool(value.strip()) and encodable(value)


# ---------------------------------------------------------------- portas

def bindable(family, address, port):
    """True/False para o bind; None quando a família não existe aqui (sem IPv6 não é porta ocupada)."""
    try:
        probe = socket.socket(family, socket.SOCK_STREAM)
    except OSError as exc:
        # Só "sem IPv6" vira None; falta de descritores (EMFILE) numa sondagem não pode virar porta livre.
        if family == socket.AF_INET6 and exc.errno in (errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT):
            return None
        raise
    try:
        # Sem SO_REUSEADDR de propósito: com ele o bind passaria por cima de quem já usa a porta.
        if family == socket.AF_INET6:
            probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        probe.bind((address, port))
        return True
    except OSError as exc:
        if family == socket.AF_INET6 and exc.errno not in (errno.EADDRINUSE, errno.EACCES):
            return None
        return False
    finally:
        probe.close()


def port_is_free(port):
    checks = [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET, '0.0.0.0')]
    if socket.has_ipv6:
        checks.append((socket.AF_INET6, '::'))
    return all(bindable(family, address, port) is not False for family, address in checks)


def free_ports(count, start, end, avoid=()):
    if not all(is_int(value) for value in (count, start, end)):
        raise ValueError('count, start e end devem ser inteiros')
    if count < 1:
        raise ValueError('--count deve ser maior ou igual a 1')
    if not 1 <= start <= end <= 65535:
        raise ValueError('intervalo inválido: exige 1 <= start <= end <= 65535')
    skip = set(avoid)
    if not all(is_int(port) and 1 <= port <= 65535 for port in skip):
        raise ValueError('--avoid aceita somente portas de 1 a 65535')
    free, busy, avoided = [], [], []
    for port in range(start, end + 1):
        if len(free) == count:
            break
        # --avoid vem antes do bind: é justamente a porta que o bind local diria estar livre.
        if port in skip:
            avoided.append(port)
        elif port_is_free(port):
            free.append(port)
        else:
            busy.append(port)
    if len(free) < count:
        raise ValueError(f'intervalo {start}-{end} esgotado: {len(free)} de {count} porta(s) livre(s) '
                         f'(achadas: {free}); ampliar --start/--end ou rever --avoid')
    return {'free': free, 'busy': busy, 'avoided': avoided, 'range': [start, end], 'note': PORTS_NOTE}


def parse_avoid(values):
    ports = []
    for piece in ','.join(values or []).split(','):
        if piece.strip():
            try:
                ports.append(int(piece))
            except ValueError:
                raise ValueError(f'--avoid inválido: {piece.strip()!r} não é número de porta') from None
    return ports


# ---------------------------------------------------------------- spec do dublê

def unknown_keys(data, allowed, where, problems):
    extra = sorted(str(key) for key in set(data) - allowed)
    if extra:
        # Chave com erro de digitação (delay em vez de delay_ms) mudaria o teste em silêncio.
        problems.append(f'{where}: chave(s) desconhecida(s): {", ".join(extra)}')


def check_response(item, where, problems):
    if not isinstance(item, dict):
        problems.append(f'{where}: deve ser objeto')
        return None
    unknown_keys(item, RESPONSE_KEYS, where, problems)
    status = item.get('status')
    if not is_int(status) or not 100 <= status <= 599:
        problems.append(f'{where}.status: inteiro de 100 a 599 obrigatório')
        status = None
    elif status < 200:
        # 1xx não encerra a troca: o cliente ficaria pendurado e o log afirmaria uma resposta que não houve.
        problems.append(f'{where}.status: {status} é resposta interina do HTTP e o cliente ficaria esperando '
                        'a final; declarar de 200 a 599')
        status = None
    headers = {}
    declared = item.get('headers', {})
    if not isinstance(declared, dict):
        problems.append(f'{where}.headers: deve ser objeto nome → valor')
        declared = {}
    for name, value in declared.items():
        if not isinstance(name, str) or not HEADER_NAME.fullmatch(name):
            problems.append(f'{where}.headers: nome de cabeçalho inválido {name!r}')
        elif name.lower() in ('content-length', 'transfer-encoding'):
            problems.append(f'{where}.headers: {name} é calculado pelo dublê')
        elif not (isinstance(value, str) or is_number(value)) or '\r' in str(value) or '\n' in str(value):
            problems.append(f'{where}.headers.{name}: valor deve ser texto de uma linha')
        elif not encodable(str(value), 'latin-1'):
            problems.append(f'{where}.headers.{name}: valor fora de latin-1 não trafega em cabeçalho HTTP; usar ASCII')
        else:
            headers[name] = str(value)
    result = {'status': status, 'headers': headers}
    if 'json' in item and 'body' in item:
        problems.append(f'{where}: usar só um de json/body')
    elif 'json' in item:
        try:
            json.dumps(item['json'], ensure_ascii=False, allow_nan=False).encode('utf-8')
            result['json'] = item['json']
        except (TypeError, ValueError):
            problems.append(f'{where}.json: valor não serializável em JSON UTF-8 (NaN, Infinity, surrogate solto)')
    elif 'body' in item:
        if isinstance(item['body'], str) and encodable(item['body']):
            result['body'] = item['body']
        else:
            problems.append(f'{where}.body: deve ser texto codificável em UTF-8')
    if status in BODILESS and ('json' in item or item.get('body')):
        problems.append(f'{where}: status {status} não admite corpo')
    return result


def check_route(item, where, problems):
    if not isinstance(item, dict):
        problems.append(f'{where}: deve ser objeto')
        return None
    unknown_keys(item, ROUTE_KEYS, where, problems)
    result = {}
    if 'name' in item:
        if required_text(item['name']):
            result['name'] = item['name'].strip()
        else:
            problems.append(f'{where}.name: quando presente, deve ser texto')
    method = item.get('method')
    if isinstance(method, str) and method.upper() in METHODS | {'ANY'}:
        result['method'] = method.upper()
    else:
        problems.append(f'{where}.method: obrigatório, um de {", ".join(sorted(METHODS))} ou ANY')
    if ('path' in item) == ('path_regex' in item):
        problems.append(f'{where}: exatamente um de path/path_regex')
    elif 'path' in item:
        path = item['path']
        if not isinstance(path, str) or not path.startswith('/') or '?' in path or '#' in path:
            problems.append(f'{where}.path: texto iniciado por / e sem query string (o casamento ignora a query)')
        else:
            result['path'] = path
    else:
        try:
            re.compile(item['path_regex'])
            result['path_regex'] = item['path_regex']
        except (re.error, TypeError) as exc:
            problems.append(f'{where}.path_regex: expressão regular inválida ({exc})')
    delay = item.get('delay_ms', 0)
    # A comparação dupla também barra NaN e Infinity, que o JSON do Python aceita e o sleep não.
    if is_number(delay) and 0 <= delay <= DELAY_LIMIT_MS:
        result['delay_ms'] = delay
    else:
        problems.append(f'{where}.delay_ms: número de 0 a {DELAY_LIMIT_MS}')
    responses = item.get('responses')
    if not isinstance(responses, list) or not responses:
        problems.append(f'{where}.responses: lista não vazia obrigatória')
        responses = []
    result['responses'] = [check_response(response, f'{where}.responses[{index}]', problems)
                           for index, response in enumerate(responses)]
    return result


def validate_spec(data):
    """Devolve o spec normalizado ou levanta ValueError listando todos os problemas de uma vez."""
    if not isinstance(data, dict):
        raise ValueError('spec inválido: deve ser objeto JSON')
    problems = []
    unknown_keys(data, SPEC_KEYS, 'spec', problems)
    if not required_text(data.get('name')):
        problems.append('name: texto obrigatório')
    routes = data.get('routes')
    if not isinstance(routes, list) or not routes:
        problems.append('routes: lista não vazia obrigatória')
        routes = []
    checked = [check_route(route, f'routes[{index}]', problems) for index, route in enumerate(routes)]
    names = [route['name'] for route in checked if route and 'name' in route]
    for name in sorted({name for name in names if names.count(name) > 1}):
        # O log identifica a rota pelo name; repetido, a prova deixaria de dizer quem respondeu.
        problems.append(f'routes: name repetido {name!r}')
    unredacted = data.get('unredacted_headers', [])
    if not isinstance(unredacted, list) or not all(isinstance(name, str) and HEADER_NAME.fullmatch(name)
                                                   for name in unredacted):
        problems.append('unredacted_headers: lista de nomes de cabeçalho')
        unredacted = []
    for name in unredacted:
        if any(word in name.lower() for word in ALWAYS_REDACTED):
            problems.append(f'unredacted_headers: {name} é sempre removido do log')
    if problems:
        raise ValueError('spec inválido: ' + '; '.join(problems))
    return {'name': data['name'].strip(), 'routes': checked,
            'unredacted_headers': sorted({name.lower() for name in unredacted})}


def load_spec(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'spec não é JSON válido: {exc}') from None
    return validate_spec(data)


# ---------------------------------------------------------------- servidor do dublê

def render(response):
    headers = dict(response['headers'])
    if 'json' in response:
        text = json.dumps(response['json'], ensure_ascii=False, allow_nan=False)
        payload, kind = text.encode('utf-8'), 'application/json'
    else:
        payload, kind = response.get('body', '').encode('utf-8'), 'text/plain'
    if payload and not any(name.lower() == 'content-type' for name in headers):
        headers['Content-Type'] = f'{kind}; charset=utf-8'
    return response['status'], headers, payload


class Routes:
    def __init__(self, spec):
        self.lock = threading.Lock()
        self.items = [{'label': route.get('name') or f'routes[{index}]',
                       'method': route['method'],
                       'path': route.get('path'),
                       'regex': re.compile(route['path_regex']) if 'path_regex' in route else None,
                       'delay': route['delay_ms'] / 1000,
                       'responses': [render(response) for response in route['responses']],
                       'calls': 0} for index, route in enumerate(spec['routes'])]

    def pick(self, method, path):
        for route in self.items:
            if route['method'] not in ('ANY', method):
                continue
            if route['regex'].fullmatch(path) if route['regex'] else route['path'] == path:
                with self.lock:
                    index = min(route['calls'], len(route['responses']) - 1)
                    route['calls'] += 1
                return route, index
        return None, None


def plain_path(value):
    """Absoluto sem seguir links: resolve() trocaria o caminho pedido pelo alvo do link, e o modo exclusivo
    criaria arquivo e diretórios fora dele (além de o contrato de evidências recusar link depois)."""
    path = Path(os.path.abspath(value))
    for piece in (path, *path.parents):
        if piece.is_symlink() or (hasattr(piece, 'is_junction') and piece.is_junction()):
            raise ValueError(f'caminho do log passa por link de filesystem ({piece}); informar o caminho real')
    return path


class RequestLog:
    def __init__(self, path):
        self.path = plain_path(path)
        self.lock = threading.Lock()
        self.count = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # 0o600: o corpo e a query vão crus para o log e podem carregar credencial de teste.
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
        except FileExistsError:
            raise ValueError(f'log já existe e provas não são sobrescritas: {self.path}') from None
        self.stream = os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n')

    def write(self, record, request=True):
        line = json.dumps(record, ensure_ascii=False) + '\n'
        with self.lock:
            if not self.stream.closed:
                self.stream.write(line)
                self.stream.flush()
                if request:
                    self.count += 1

    def close(self):
        with self.lock:
            self.stream.close()


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 para o http.server responder Expect: 100-continue e manter keep-alive como uma API real.
    protocol_version = 'HTTP/1.1'

    def version_string(self):
        return 'qa-bot-mock'

    def log_message(self, format, *args):
        pass

    def __getattr__(self, name):
        # Verbo fora da lista também chega aqui: precisa aparecer no log como não declarado,
        # em vez de sumir no 501 genérico do http.server.
        if name.startswith('do_'):
            return self.answer
        raise AttributeError(name)

    def handle_one_request(self):
        # ClientHello de TLS quase nunca traz \n: o readline do http.server esperaria o cliente desistir,
        # sem linha no log, no erro de configuração mais comum (alvo em https contra o dublê).
        # Nenhum método HTTP começa com 0x16.
        try:
            first = self.rfile.peek(1)[:1]
        except OSError:
            first = b''
        if first == b'\x16':
            self.raw_requestline, self.requestline, self.request_version, self.command = b'', '', '', ''
            self.reject(400, TLS_REASON)
        else:
            super().handle_one_request()

    def send_error(self, code, message=None, explain=None):
        # Chega aqui o que o http.server recusa antes de answer() (linha inválida, 414, 431, 505).
        # Chamada que o alvo fez precisa aparecer no log mesmo assim, e a recusa sai em JSON como as outras.
        if self.raw_requestline.startswith(b'PRI * HTTP/2'):
            reason = H2_REASON
        else:
            reason = PARSER_ERRORS.get(int(code), 'requisição que o servidor HTTP não aceita')
            if message:
                reason += f' ({str(message)[:200]})'
        self.reject(int(code), reason)

    def reject(self, status, reason):
        raw = self.raw_requestline
        line = raw[:REQUEST_LINE_LOG].decode('utf-8', 'replace').rstrip('\r\n')
        words = line.split()
        # self.command/self.path podem ser os da requisição anterior da mesma conexão; vale a linha crua.
        method = words[0] if words and HEADER_NAME.fullmatch(words[0]) else None
        path, _, query = (words[1] if method and len(words) > 1 else '').partition('?')
        error = f'requisição recusada antes das rotas: {reason}'
        record = {'at': now(), 'method': method, 'path': path or None, 'query': query, 'headers': {},
                  'request_line': line, 'body_bytes': 0, 'route': None, 'response_index': None,
                  'status': status, 'error': error}
        if len(raw) > REQUEST_LINE_LOG:
            record['request_line_truncated'] = True
        _, headers, payload = self.refusal(status, error, method, path or None)
        headers['Connection'] = 'close'
        self.close_connection = True
        # O http.server recusa a linha ainda como HTTP/0.9 e, assim, omitiria status e cabeçalhos da recusa.
        self.request_version = self.protocol_version
        self.deliver(record, headers, payload)

    def exactly(self, size):
        if size < 0:
            raise ValueError(size)
        while size:
            block = self.rfile.read(min(size, 65536))
            if not block:
                raise ValueError(size)
            size -= len(block)
            yield block

    def blocks(self):
        # Clientes .NET/Java mandam JSON em chunked, sem Content-Length; ignorar deixaria a prova sem corpo
        # e o resto do corpo seria lido como a próxima requisição da conexão.
        if 'chunked' in self.headers.get('Transfer-Encoding', '').lower():
            while True:
                size = int(self.rfile.readline(LINE_LIMIT).split(b';', 1)[0].strip(), 16)
                if size == 0:
                    break
                yield from self.exactly(size)
                self.rfile.readline(LINE_LIMIT)
            while self.rfile.readline(LINE_LIMIT) not in (b'\r\n', b'\n', b''):
                pass
        else:
            yield from self.exactly(int(self.headers.get('Content-Length') or 0))

    def read_body(self, record):
        kept, total, problem = bytearray(), 0, None
        try:
            for block in self.blocks():
                total += len(block)
                if len(kept) < BODY_LIMIT:
                    kept += block[:BODY_LIMIT - len(kept)]
        except (ValueError, OSError):
            # OSError: cliente que derruba a conexão (RST) no meio do corpo também chamou e precisa ficar no log.
            problem = 'corpo ilegível: Content-Length/chunked malformado ou conexão encerrada antes do fim'
        try:
            # final=False só perdoa o caractere que o limite cortou ao meio; byte inválido continua em base64.
            record['body_text'] = codecs.getincrementaldecoder('utf-8')().decode(bytes(kept), total <= BODY_LIMIT)
        except UnicodeDecodeError:
            record['body_base64'] = base64.b64encode(bytes(kept)).decode('ascii')
        record['body_bytes'] = total
        if total > BODY_LIMIT:
            record['body_truncated'] = True
        return problem

    def logged_headers(self):
        headers = {}
        for name, value in self.headers.items():
            lower = name.lower()
            if lower not in self.server.unredacted and any(word in lower for word in SENSITIVE):
                headers[name] = REDACTED
            else:
                headers[name] = f'{headers[name]}, {value}' if name in headers else value
        return headers

    def refusal(self, status, message, method, path):
        data = {'mock': self.server.spec_name, 'error': message, 'method': method, 'path': path}
        return render({'status': status, 'headers': {}, 'json': data})

    def answer(self):
        path, _, query = self.path.partition('?')
        record = {'at': now(), 'method': self.command, 'path': path, 'query': query,
                  'headers': self.logged_headers()}
        problem = self.read_body(record)
        route, index = (None, None) if problem else self.server.routes.pick(self.command.upper(), path)
        if problem:
            status, headers, payload = self.refusal(400, problem, self.command, path)
            headers['Connection'] = 'close'
        elif route is None:
            status, headers, payload = self.refusal(501, 'rota não declarada no dublê', self.command, path)
        else:
            status, headers, payload = route['responses'][index]
        record.update(route=route['label'] if route else None, response_index=index, status=status)
        if problem:
            record['error'] = problem
        self.deliver(record, headers, payload, route['delay'] if route else 0)

    def deliver(self, record, headers, payload, delay=0):
        # O registro vem antes da resposta (e do atraso): quem recebeu a resposta já encontra a linha no log,
        # e cliente que desiste por timeout continua provado.
        self.server.log.write(record)
        try:
            if delay:
                time.sleep(delay)
            self.send_response(record['status'])
            for name, value in headers.items():
                self.send_header(name, value)
            if record['status'] != 204:
                self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            if (record['method'] or '').upper() != 'HEAD' and payload:
                self.wfile.write(payload)
        except Exception as exc:
            self.close_connection = True
            # A linha acima já afirmou o status. Quando o envio falha de forma visível, esta segunda linha impede
            # a prova de dizer que o cliente recebeu; a ausência dela não prova entrega (o SO aceita escrita
            # em conexão que o cliente já abandonou).
            self.server.log.write({'at': now(), 'method': record['method'], 'path': record['path'],
                                   'route': record['route'], 'status': record['status'],
                                   'response_error': f'resposta não entregue: {exc}'}, request=False)


class MockServer(ThreadingHTTPServer):
    # No Windows SO_REUSEADDR deixaria o dublê tomar uma porta em uso. No POSIX dispensa o TIME_WAIT de um dublê
    # recém-encerrado (reiniciar na mesma porta é o uso normal); no Linux o bind ainda recusa porta com alguém
    # escutando, mas em BSD/macOS endereço específico e curinga convivem: por isso listening() sonda antes.
    allow_reuse_address = os.name != 'nt'
    log = None
    routes = None
    spec_name = ''
    unredacted = frozenset()

    def __init__(self, address, handler):
        if ':' in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, handler)

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            # Mesmo critério de ports: sem isto, --bind :: escutaria também IPv4 de todas as interfaces.
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        # HTTPServer.server_bind resolve o FQDN do host; DNS reverso lento atrasaria o início sem ganho.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    @property
    def port(self):
        return self.server_address[1]

    @property
    def url(self):
        host = self.server_address[0]
        return f'http://[{host}]:{self.port}' if ':' in host else f'http://{host}:{self.port}'

    def handle_error(self, request, client_address):
        # Cliente que desiste no meio não é defeito do dublê; o rastro confundiria quem lê erros JSON no stderr.
        if not isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            super().handle_error(request, client_address)

    def server_close(self):
        super().server_close()
        if self.log is not None:
            self.log.close()


def listening(bind, port):
    """Endereços em que alguém já aceita conexão na porta. connect em vez de bind sem SO_REUSEADDR: o TIME_WAIT
    de um dublê recém-encerrado não é ocupante, e serviço que só escuta em ::1 (ou no curinga, em BSD/macOS)
    não barra o bind em 127.0.0.1, mas recebe o que o alvo manda para localhost."""
    hosts = ['127.0.0.1', '::1'] + ([] if bind in ('127.0.0.1', '::1', '0.0.0.0', '::') else [bind])
    found = []
    for host in hosts:
        try:
            socket.create_connection((host, port), timeout=0.5).close()
            found.append(host)
        except OSError:
            pass
    return found


def build_server(spec, bind, port, log_path):
    """Servidor já escutando, sem serve_forever; a porta real fica em .port e o endereço em .url."""
    spec = validate_spec(spec)
    # Respostas renderizadas antes da porta e do log: nada do spec pode falhar depois que eles existem.
    routes = Routes(spec)
    if not is_int(port) or not 0 <= port <= 65535:
        raise ValueError('--port deve estar entre 0 e 65535')
    if not isinstance(bind, str) or not bind.strip():
        # --bind "$GW" com variável vazia escutaria em todas as interfaces sem ninguém ter pedido.
        raise ValueError('--bind não pode ser vazio: usar 127.0.0.1, o gateway da rede do contêiner '
                         'ou 0.0.0.0 de forma explícita')
    log_path = plain_path(log_path)
    if log_path.exists():
        raise ValueError(f'log já existe e provas não são sobrescritas: {log_path}')
    taken = listening(bind, port) if port else []
    if taken:
        raise ValueError(f'porta {port} já está em uso (alguém aceita conexão em {", ".join(taken)}); '
                         'escolher outra com o subcomando ports')
    try:
        server = MockServer((bind, port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise ValueError(f'porta {port} já está em uso em {bind}; escolher outra com o subcomando ports') from None
        raise ValueError(f'não foi possível escutar em {bind}:{port}: {exc.strerror or exc}') from None
    try:
        # O log só nasce depois do bind: porta recusada não deixa arquivo vazio barrando a nova tentativa.
        server.log = RequestLog(log_path)
    except BaseException:
        server.server_close()
        raise
    server.spec_name, server.routes = spec['name'], routes
    server.unredacted = frozenset(spec['unredacted_headers'])
    return server


def serve(args):
    server = build_server(load_spec(args.spec), args.bind, args.port, args.log)
    stop = threading.Event()
    previous = {}
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
    try:
        for name in ('SIGINT', 'SIGTERM'):
            if hasattr(signal, name):
                number = getattr(signal, name)
                previous[number] = signal.signal(number, lambda *_: stop.set())
        thread.start()
        emit({'mock': server.spec_name, 'url': server.url, 'pid': os.getpid(), 'log': str(server.log.path),
              'routes': len(server.routes.items), 'started_at': now(), 'note': MOCK_NOTE})
        # Espera em fatias: no Windows um wait sem prazo não é interrompido pelo sinal.
        while not stop.wait(0.5):
            pass
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        for number, handler in previous.items():
            signal.signal(number, handler)
    try:
        emit({'stopped_at': now(), 'requests': server.log.count})
    except BrokenPipeError:
        # Quem lançou o dublê pode ter fechado o pipe depois de ler a linha de início; encerrar continua limpo.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(f'uso inválido: {message}')


def main(argv=None):
    parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    ports = sub.add_parser('ports', help='portas livres agora em 127.0.0.1, 0.0.0.0 e ::')
    ports.add_argument('--count', type=int, default=1)
    ports.add_argument('--start', type=int, default=18000)
    ports.add_argument('--end', type=int, default=18999)
    ports.add_argument('--avoid', action='append', help='portas a pular, separadas por vírgula')
    mock = sub.add_parser('mock', help='servir dublê HTTP declarado em spec JSON; não sobrescreve log')
    mock.add_argument('--spec', required=True)
    mock.add_argument('--port', type=int, required=True, help='0 deixa o SO escolher')
    mock.add_argument('--log', required=True,
                      help='requests.jsonl novo; diretórios pais são criados. Caminho, query e corpo ficam crus '
                           'no log (só cabeçalho sensível é removido): revisar antes de usar como evidência')
    mock.add_argument('--bind', default='127.0.0.1', help='endereço de escuta; vazio é recusado')
    try:
        args = parser.parse_args(argv)
        if args.command == 'mock':
            return serve(args)
        emit(free_ports(args.count, args.start, args.end, parse_avoid(args.avoid)), indent=2)
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
