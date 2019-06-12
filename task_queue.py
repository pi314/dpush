import json
import os
import re
import socket
import socketserver
import sys

from queue import Queue
from threading import Thread

from . import HOST, PORT

from .task import Task
from .utils import log_create, log_info, log_error
from .worker import do_job


task_queue = Queue()
current_task = None


def dump_queue():
    data = {}
    if current_task:
        data['working'] = {}
        data['working']['cwd'] = current_task.cwd
        data['working']['cmd'] = current_task.cmd
        data['working']['args'] = current_task.args

    data['pending'] = []
    for t in list(task_queue.queue):
        i = {}
        i['cwd'] = t.cwd
        i['cmd'] = t.cmd
        i['args'] = t.args
        data['pending'].append(i)

    return data


class MyTCPHandler(socketserver.StreamRequestHandler):
    def readline(self):
        return self.rfile.readline().strip().decode('utf-8')

    def writeline(self, line):
        self.wfile.write((line.rstrip() + '\n').encode('utf-8'))

    def writejson(self, obj):
        self.writeline(json.dumps(obj))

    def writeresult(self, status, reason):
        res = {}
        res['status'] = status
        res['reason'] = reason
        self.writejson(res)

    def handle(self):
        try:
            req = json.loads(self.readline())
        except json.decoder.JSONDecodeError:
            self.writeresult('400 Bad Request', 'Invalid format')
            return

        cmd = req.get('cmd', None)
        if not cmd:
            self.writeresult('400 Bad Request', 'Should provide cmd')
            return

        if cmd == 'dumpjson':
            self.handle_dumpjson()
        elif cmd == 'dump':
            self.handle_dump()
        elif cmd == 'schedule_quit':
            self.handle_schedule_quit()
        else:
            self.handle_cmd(req)

    def handle_dumpjson(self):
        data = dump_queue()
        self.writejson(data)

    def handle_dump(self):
        if current_task:
            self.writeline(str(current_task))

        for t in list(task_queue.queue):
            self.writeline(str(t))

    def handle_schedule_quit(self):
        task_queue.put(Task(None, 'quit', []))
        self.writeresult('202 Accepted', 'quit')

    def handle_cmd(self, req):
        cmd = req['cmd']
        cwd = req.get('cwd', None)
        if not cwd:
            self.writeresult('400 Bad Request', 'Should provide cwd')
            return

        args = req.get('args', None)
        if not args:
            self.writeresult('400 Bad Request', 'No arguments provided')
            return

        elif type(args) == str:
            self.writeresult('400 Bad Request', 'Arguments should be a list')
            return

        task_queue.put(Task(cwd, cmd, args))

        self.writeresult('202 Accepted', ', '.join(args))


def server_frontend():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((HOST, PORT), MyTCPHandler) as server:
        server.serve_forever()


def send_req(req):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((HOST, PORT))

            def writeline(line):
                sock.sendall((line + '\n').encode('utf-8'))

            def writejson(obj):
                writeline(json.dumps(obj))

            writejson(req)

            sock.shutdown(socket.SHUT_WR)

            res = b''
            while True:
                data = sock.recv(1024)
                if not data: break
                res += data

            try:
                print(res.decode('utf-8').strip())
            except (BrokenPipeError, IOError):
                sys.stderr.close()

            try:
                sock.shutdown(socket.SHUT_RD)
            except OSError:
                pass

            try:
                sock.close()
            except OSError:
                pass

    except ConnectionRefusedError:
        log_error('Task queue not running')


# =============================================================================
# Public interface
# -----------------------------------------------------------------------------
def start():
    global current_task

    t = Thread(target=server_frontend)
    t.daemon = True
    t.start()

    ret = 0

    log_create()

    try:
        while True:
            current_task = task_queue.get()

            if current_task.cmd == 'quit':
                current_task.status = 'info'
                log_info()
                log_info(str(current_task))
                do_job(current_task)
                current_task.status = 'succeed'
                break

            os.chdir(current_task.cwd)
            current_task.status = 'working'
            log_info()
            log_info(str(current_task))
            do_job(current_task)
            log_info()
            log_info(str(current_task))
            if current_task.status == 'interrupted':
                ret = 1
                break

            current_task = None

            if task_queue.empty():
                log_info()
                log_info('[info] Task queue empty')

    except KeyboardInterrupt:
        log_error('KeyboardInterrupt')

    while not task_queue.empty():
        current_task = task_queue.get()
        current_task.status = 'canceled'
        log_info()
        log_info(str(current_task))

    return ret


def add_task(cmd, argv):
    if sys.stdin.isatty():
        req = {}
        req['cwd'] = os.getcwd()
        req['cmd'] = cmd
        req['args'] = argv
        send_req(req)

    else:
        files = []
        for line in sys.stdin:
            line = line.strip()
            if not line: continue
            files.append(line)

        for pushee in files:
            req = {}
            req['cwd'] = os.getcwd()
            req['cmd'] = cmd
            req['args'] = [pushee]
            send_req(req)


def dumpjson():
    req = {}
    req['cmd'] = 'dumpjson'
    send_req(req)


def dump():
    req = {}
    req['cmd'] = 'dump'
    send_req(req)


def load():
    data = ''
    try:
        for line in sys.stdin:
            data += line
    except KeyboardInterrupt:
        return 1

    try:
        data = json.loads(data)

    except json.decoder.JSONDecodeError:
        log_error('Invalid JSON string')
        log_error('Parsing with alternative format')
        return load_alternative(data)

    if 'working' in data:
        w = data['working']
        t = Task(w['cwd'], w['cmd'], w['args'])
        task_queue.put(t)

        for p in data['pending']:
            t = Task(p['cwd'], p['cmd'], p['args'])
            task_queue.put(t)

    start()


def load_alternative(data):
    cwd = None
    cmd = None
    args = []

    def enqueue(cwd, cmd, args):
        if cmd == 'quit':
            pass

        elif not cwd: return
        elif not cmd: return
        elif not args: return

        task_queue.put(Task(cwd, cmd, args))

    for line in data.split('\n'):
        line = line.rstrip()
        m = re.match(r'^\[(?:working|pending|interrupted|canceled)\] ([^:]+):(.*)$', line)
        if not m:
            enqueue(cwd, cmd, args)
            cwd = None
            cmd = None
            args = []

        elif m.group(1) == 'cwd':
            cwd = m.group(2)

        elif m.group(1) == 'cmd':
            cmd = m.group(2)

        elif m.group(1) == 'arg':
            args.append(m.group(2))

    enqueue(cwd, cmd, args)
    start()


def schedule_quit():
    req = {}
    req['cmd'] = 'schedule_quit'
    send_req(req)

# -----------------------------------------------------------------------------
# Public interface
# =============================================================================
