"""Live Level 6 dashboard: scores, bounds, running jobs, agents, notes.  Local only, standard library only.

usage (from the repo root):   python3 tools/dashboard/serve.py [--port 8765]
then open http://127.0.0.1:8765

Everything is read from disk on request; nothing here changes results.  The only things it writes are
under work/dashboard/: history.jsonl (score snapshots) and notes.jsonl (notes typed into the page).
Agents and scripts post to the page with tools/dashboard/post.py (work/dashboard/events.jsonl).
"""
import argparse, csv, glob, hashlib, json, os, re, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
L6 = f'{ROOT}/work/level6'
RES = f'{ROOT}/results/level6'
DASH = f'{ROOT}/work/dashboard'
KEYS = ['2-medium', '3-large', '4-enormous']          # the files that count on the website
CLAUDE_PROJECTS = os.path.expanduser('~/.claude/projects')
CONFIG = json.load(open(f'{HERE}/config.json'))
HZ = os.sysconf('SC_CLK_TCK')


# ---------------------------------------------------------------- small helpers

def read(path, default=''):
    try:
        with open(path, errors='replace') as f:
            return f.read()
    except OSError:
        return default


def tail_lines(path, n=8, max_bytes=65536):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - max_bytes))
            return f.read().decode(errors='replace').splitlines()[-n:]
    except OSError:
        return []


def jsonl(path):
    out = []
    for line in read(path).splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def programs(path):
    text = read(path).strip('\n')
    return text.split('\n\n') if text else []


def prog_lines(p):
    return len(p.split('\n'))


def prog_hash(p):
    return hashlib.md5(p.strip('\n').encode()).hexdigest()


# ---------------------------------------------------------------- scores, bounds, cases

def lower_bounds():
    """{(key, case): row of bounds.csv}, lb raised by newer bound files (bounds_medium2.csv)."""
    rows = {}
    for r in csv.DictReader(read(f'{RES}/bounds.csv').splitlines()):
        rows[(r['file'], int(r['case']))] = r
    newer = [('2-medium', f'{RES}/bounds_medium2.csv')] + [(k, f'{RES}/bounds2_{k}.csv') for k in KEYS]
    for key, path in newer:
        for r in csv.DictReader(read(path).splitlines()):
            try:
                row = rows.get((key, int(r['case'])))
                if row is not None and r.get('lb') and int(r['lb']) > int(row['lb'] or 0):
                    row['lb'] = r['lb']; row['method'] = 'satmodel2'
            except (KeyError, ValueError):
                pass                    # file being rewritten right now
    return rows


def windows_done():
    """{(key, case): program hash whose exact windows were all checked}."""
    done = {}
    for path in glob.glob(f'{L6}/overnight*/windows_done.json'):
        d = os.path.basename(os.path.dirname(path))
        key = d[len('overnight_'):] if d.startswith('overnight_') else '3-large'
        try:
            for c, h in json.load(open(path)).items():
                done[(key, int(c))] = h
        except (OSError, ValueError):
            pass
    return done


def cases_and_scores():
    bounds = lower_bounds(); wdone = windows_done()
    cases, files, attention = [], {}, []
    for key in KEYS:
        live = programs(f'{L6}/best/out_level-6_{key}.txt')
        committed = programs(f'{RES}/best/out_level-6_{key}.txt')
        f = dict(key=key, best=0, committed=sum(map(prog_lines, committed)), lb=0, cases=len(live),
                 proven=0, gap=0, open=0)
        for i, p in enumerate(live):
            n = prog_lines(p); r = bounds.get((key, i), {})
            lb = int(r.get('lb') or 0)
            imp = f'{RES}/improved/{key}_{i}.txt'
            unmerged = os.path.exists(imp) and prog_lines(read(imp).strip('\n')) < n
            cases.append(dict(key=key, case=i, R=int(r.get('R') or 0), count=int(r.get('count') or 0),
                              cells=int(r.get('cells') or 0), best=n, lb=lb, gap=max(0, n - lb),
                              proven=lb >= n, method=r.get('method', ''),
                              windows=wdone.get((key, i)) == prog_hash(p), unmerged=unmerged))
            f['best'] += n; f['lb'] += lb
            if lb >= n:
                f['proven'] += 1
            else:
                f['open'] += 1; f['gap'] += n - lb
            if unmerged:
                attention.append(dict(level='warn', title=f'{key} case {i}: unmerged window win',
                                      text='run tools/level6/merge_improved.py'))
        if f['best'] != f['committed']:
            attention.append(dict(level='info', title=f'{key}: best ({f["best"]}) not committed yet',
                                  text=f'committed {f["committed"]}; copy work/level6/best to results/level6/best and commit'))
        files[key] = f
    return cases, files, attention


_git_cache = {}


def git_history():
    """Score of every commit that changed results/level6/best/, oldest first."""
    out = subprocess.run(['git', 'log', '--reverse', '--format=%H|%ct|%s', '--', 'results/level6/best'],
                         cwd=ROOT, capture_output=True, text=True).stdout
    points = []
    for line in out.splitlines():
        h, ts, subject = line.split('|', 2)
        if h not in _git_cache:
            per = {}
            for key in KEYS:
                text = subprocess.run(['git', 'show', f'{h}:results/level6/best/out_level-6_{key}.txt'],
                                      cwd=ROOT, capture_output=True, text=True).stdout.strip('\n')
                per[key] = sum(map(prog_lines, text.split('\n\n'))) if text else None
            _git_cache[h] = per
        points.append(dict(t=int(ts), source='commit', subject=subject, **_git_cache[h]))
    return points


def commits(n=40):
    out = subprocess.run(['git', 'log', f'-{n}', '--format=%h|%ct|%s'], cwd=ROOT,
                         capture_output=True, text=True).stdout
    return [dict(hash=h, t=int(ts), subject=s) for h, ts, s in (l.split('|', 2) for l in out.splitlines())]


def progress_points():
    """Round results from the optimiser logs ('[HH:MM:SS] round N done: <key> best X').  The logs only
    have the clock time: real times are chained backwards from the file's modification time, using
    the clock difference between consecutive lines (a small backwards step is the DST change)."""
    pts = []
    for path in glob.glob(f'{L6}/overnight*/progress.log'):
        stamped = re.findall(r'^\[(\d+):(\d+):(\d+)\] (.*)$', read(path), re.M)
        if not stamped:
            continue
        clock = [int(h) * 3600 + int(m) * 60 + int(sec) for h, m, sec, _ in stamped]
        mt = os.path.getmtime(path); lt = time.localtime(mt)
        t = mt - ((lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec - clock[-1]) % 86400)
        for i in range(len(stamped) - 1, -1, -1):
            if i < len(stamped) - 1:
                d = (clock[i + 1] - clock[i]) % 86400
                if d > 82800:            # clock went back by < 1 h: DST end
                    d = d - 86400 + 3600
                t -= d
            m = re.match(r'round \d+ done: (\S+) best (\d+)', stamped[i][3])
            if m:
                key = {'large': '3-large', 'enormous': '4-enormous', 'medium': '2-medium'}.get(m.group(1), m.group(1))
                pts.append(dict(t=int(t), source=f'{key} optimiser round', **{key: int(m.group(2))}))
    return pts


def score_history(files):
    """Every known score change: contest end, commits, optimiser rounds, live snapshots, now.
    Partial points (one file) are completed by carrying the other files forward; points that do
    not change the total are dropped."""
    raw = [dict(t=CONFIG['contest_end']['t'], source='contest end', **CONFIG['contest_end']['scores'])]
    raw += [p for p in git_history() if any(p.get(k) for k in KEYS)]
    raw += progress_points() + jsonl(f'{DASH}/history.jsonl')
    raw.append(dict(t=int(time.time()), source='now', **{k: files[k]['best'] for k in KEYS}))
    raw.sort(key=lambda p: p['t'])
    cur = dict(CONFIG['contest_end']['scores']); out = []
    for p in raw:
        for k in KEYS:
            if p.get(k):
                cur[k] = min(cur[k], p[k])      # the kept best never gets worse
        q = dict(t=p['t'], source=p['source'], subject=p.get('subject', ''), **cur)
        q['total'] = sum(cur[k] for k in KEYS)
        if not out or q['total'] != out[-1]['total'] or p['source'] == 'now':
            out.append(q)
    return out


# ---------------------------------------------------------------- processes / jobs

class Sampler:
    """Keeps CPU tick counters of processes and cores between polls, to turn them into percentages."""

    def __init__(self):
        self.lock = threading.Lock()
        self.prev_proc, self.prev_cpu = {}, None
        self.proc_pct, self.core_pct = {}, []
        self.last_total = None

    def sample(self):
        now = time.time(); ticks = {}
        for pid in os.listdir('/proc'):
            if pid.isdigit():
                st = read(f'/proc/{pid}/stat')
                if st:
                    parts = st[st.rfind(')') + 2:].split()
                    ticks[int(pid)] = (int(parts[11]) + int(parts[12]), int(parts[1]))   # utime+stime, ppid
        cpu = [l.split() for l in read('/proc/stat').splitlines() if re.match(r'cpu\d', l)]
        cpu = [(sum(map(int, c[1:9])), int(c[4]) + int(c[5])) for c in cpu]
        with self.lock:
            if self.prev_cpu is not None:
                dt = now - self.prev_t
                self.proc_pct = {p: 100 * (t - self.prev_proc[p][0]) / HZ / dt
                                 for p, (t, _) in ticks.items() if p in self.prev_proc}
                self.core_pct = [100 * (1 - (idle - pi) / max(1, tot - pt))
                                 for (tot, idle), (pt, pi) in zip(cpu, self.prev_cpu)]
            self.ppid = {p: pp for p, (_, pp) in ticks.items()}
            self.prev_proc, self.prev_cpu, self.prev_t = ticks, cpu, now

    def run(self):
        last_hist = 0
        while True:
            try:
                self.sample()
                if time.time() - last_hist > 60:
                    last_hist = time.time(); record_history()
            except Exception as e:          # never let the sampler die
                print('sampler:', e, flush=True)
            time.sleep(3)


SAMPLER = Sampler()


def record_history():
    _, files, _ = cases_and_scores()
    snap = {k: files[k]['best'] for k in KEYS}
    old = jsonl(f'{DASH}/history.jsonl')
    if not old or any(old[-1].get(k) != v for k, v in snap.items()):
        with open(f'{DASH}/history.jsonl', 'a') as f:
            f.write(json.dumps(dict(t=int(time.time()), source='snapshot', **snap)) + '\n')


JOB_PATTERNS = [   # (label, regex on the command line) for the "main" process of a job
    ('python', re.compile(r'python[\d.]*\s+(-u\s+)?(\S*/)?(?P<script>[\w-]+\.py)(?P<args>.*)')),
    ('cargo', re.compile(r'cargo(-ccc)?\s+ccc\s+(?P<args>.*)')),
]


def proc_info(pid):
    cmd = read(f'/proc/{pid}/cmdline').replace('\0', ' ').strip()
    try:
        cwd = os.readlink(f'/proc/{pid}/cwd')
        out = os.readlink(f'/proc/{pid}/fd/1')
    except OSError:
        cwd = out = ''
    status = read(f'/proc/{pid}/status')
    m = re.search(r'VmRSS:\s+(\d+)', status)
    return cmd, cwd, out, int(m.group(1)) * 1024 if m else 0


def job_progress(script, args, log):
    """Best-effort progress from the job's own log (its stdout file)."""
    if script == 'overnight_large.py':          # its own stdout is quiet; the rounds go to progress.log
        m = re.search(r'--key\s+(\S+)', args); key = m.group(1) if m else '3-large'
        log = f'{L6}/overnight' + ('' if key == '3-large' else f'_{key}') + '/progress.log'
    lines = tail_lines(log, 400, 1 << 20) if log else []
    prog = dict(lines=[l for l in lines if l.strip()][-6:])
    if script == 'improve.py':
        m = re.search(r'--cases\s+([\d,]+)', args)
        total = len(m.group(1).split(',')) if m else None
        full = read(log).splitlines() if log else []
        done = [l for l in full if re.match(r'\S+ case \d+: \d+ -> \d+', l)]
        cur = [l for l in full if re.match(r'\S+ case \d+ R=', l)]
        outcome = {}
        for l in full:
            mm = re.search(r': (UNKNOWN|FEASIBLE|INFEASIBLE) \(', l)
            if mm:
                outcome[mm.group(1)] = outcome.get(mm.group(1), 0) + 1
        prog.update(done=len(done), total=total, current=cur[-1] if cur else '',
                    wins=sum('spliced' in l for l in full), outcomes=outcome)
    else:
        for l in reversed(lines):
            mm = re.match(r'\s*(\d+)/(\d+)\b', l)
            if mm:
                prog.update(done=int(mm.group(1)), total=int(mm.group(2))); break
    m = re.search(r'--budget\s+(\d+)', args)
    if m:
        prog['budget'] = int(m.group(1))
    return prog


def jobs():
    with SAMPLER.lock:
        pct, ppid = dict(SAMPLER.proc_pct), dict(getattr(SAMPLER, 'ppid', {}))
    children = {}
    for p, pp in ppid.items():
        children.setdefault(pp, []).append(p)

    def tree(p):
        out = [p]
        for c in children.get(p, []):
            out += tree(c)
        return out

    found, claimed = [], set()
    boot = time.time() - float(read('/proc/uptime').split()[0])
    for pid in sorted(ppid):
        if pid in claimed:
            continue
        comm = read(f'/proc/{pid}/comm').strip()
        if not comm.startswith(('python', 'cargo')):        # skip bash/nice/timeout wrappers
            continue
        cmd, cwd, out, _ = proc_info(pid)
        if 'ccc-classic2' not in cwd + cmd or 'tools/dashboard' in cmd:
            continue
        for kind, rx in JOB_PATTERNS:
            m = rx.search(cmd)
            if not m or ' -c ' in cmd:
                continue
            pids = tree(pid); claimed.update(pids)
            st = read(f'/proc/{pid}/stat')
            start = boot + int(st[st.rfind(')') + 2:].split()[19]) / HZ if st else time.time()
            script = m.groupdict().get('script') or 'cargo ccc'
            args = m.group('args').strip()
            log = out if out.startswith('/') and os.path.isfile(out) else ''
            found.append(dict(pid=pid, name=script, args=args[:300], cpu=round(sum(pct.get(p, 0) for p in pids)),
                              rss=sum(proc_info(p)[3] for p in pids), started=int(start),
                              threads=len(pids), log=os.path.relpath(log, ROOT) if log else '',
                              progress=job_progress(script, args, log)))
            break
    return found


# ---------------------------------------------------------------- system

def system():
    temps = {}
    for h in glob.glob('/sys/class/hwmon/hwmon*'):
        name = read(f'{h}/name').strip(); t = read(f'{h}/temp1_input').strip()
        if t:
            temps[name] = int(t) / 1000
    fans = [int(read(f).strip()) for f in sorted(glob.glob('/sys/class/hwmon/hwmon*/fan*_input')) if read(f).strip()]
    mem = {k: int(v) * 1024 for k, v in re.findall(r'(\w+):\s+(\d+) kB', read('/proc/meminfo'))}
    bat = glob.glob('/sys/class/power_supply/BAT*')
    with SAMPLER.lock:
        cores = [round(c) for c in SAMPLER.core_pct]
    return dict(cores=cores, load=read('/proc/loadavg').split()[:3], temps=temps, fans=fans,
                mem_total=mem.get('MemTotal', 0), mem_avail=mem.get('MemAvailable', 0),
                swap_used=mem.get('SwapTotal', 0) - mem.get('SwapFree', 0),
                battery=dict(capacity=read(f'{bat[0]}/capacity').strip(), status=read(f'{bat[0]}/status').strip()) if bat else None,
                uptime=float(read('/proc/uptime').split()[0]))


# ---------------------------------------------------------------- agents (Claude Code subagent transcripts)

_agent_cache = {}


def parse_agent(path):
    st = os.stat(path); key = (path, st.st_mtime, st.st_size)
    if _agent_cache.get(path, (None,))[0] == key:
        return _agent_cache[path][1]
    meta = {}
    try:
        meta = json.load(open(path[:-len('.jsonl')] + '.meta.json'))
    except (OSError, ValueError):
        pass
    tools = out_tok = 0; first_t = last_t = None; last_text = last_tool = ''; ended = False
    for line in read(path).splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ts = d.get('timestamp')
        if ts:
            first_t = first_t or ts; last_t = ts
        msg = d.get('message') or {}
        if d.get('type') == 'assistant':
            out_tok += (msg.get('usage') or {}).get('output_tokens', 0)
            ended = msg.get('stop_reason') == 'end_turn'
            for c in msg.get('content') or []:
                if c.get('type') == 'text' and c.get('text', '').strip():
                    last_text = c['text'].strip()
                elif c.get('type') == 'tool_use':
                    tools += 1; inp = c.get('input') or {}
                    last_tool = f"{c.get('name')}: {inp.get('description') or inp.get('command') or inp.get('file_path') or ''}"
        elif d.get('type') == 'user' and isinstance(msg.get('content'), list):
            ended = False if any(c.get('type') == 'tool_result' for c in msg['content']) else ended
    idle = time.time() - st.st_mtime
    status = 'done' if ended and idle > 60 else ('working' if idle < 600 else 'quiet')
    info = dict(id=os.path.basename(path)[6:-6], description=meta.get('description', ''),
                type=meta.get('agentType', ''), status=status, started=first_t, last=last_t,
                idle=int(idle), tools=tools, output_tokens=out_tok,
                last_tool=last_tool[:300], last_text=last_text[-1200:])
    _agent_cache[path] = (key, info)
    return info


def agents():
    paths = glob.glob(f'{CLAUDE_PROJECTS}/*ccc-school*/*/subagents/agent-*.jsonl') + \
        glob.glob(f'{CLAUDE_PROJECTS}/*ccc-classic*/*/subagents/agent-*.jsonl')
    out = [parse_agent(p) for p in paths]
    out.sort(key=lambda a: a['last'] or '', reverse=True)
    return out


# ---------------------------------------------------------------- attention

def log_errors(job_list):
    """Tracebacks / kills in logs that changed in the last hour."""
    out = []
    logs = {os.path.join(ROOT, j['log']) for j in job_list if j['log']}
    for pat in (f'{L6}/**/*.log', f'{RES}/logs/*.log'):
        logs.update(p for p in glob.glob(pat, recursive=True) if time.time() - os.path.getmtime(p) < 3600)
    for p in sorted(logs):
        bad = [l for l in tail_lines(p, 60) if re.search(r'Traceback|Error\b|Killed|panicked|MemoryError', l)]
        if bad:
            out.append(dict(level='error', title=f'error in {os.path.relpath(p, ROOT)}', text=bad[-1][:300]))
    return out


def state():
    cases, files, attention = cases_and_scores()
    job_list = jobs(); sysinfo = system(); notes = jsonl(f'{DASH}/notes.jsonl')
    events = jsonl(f'{DASH}/events.jsonl')
    acked = {e.get('ack') for e in events if e.get('ack')}
    attention += log_errors(job_list)
    for n in notes:
        if n['id'] not in acked:
            attention.append(dict(level='note', title='your note, not answered yet', text=n['text'][:300]))
    for e in events[-200:]:
        if e.get('kind') == 'question' and e.get('id') not in acked:
            attention.append(dict(level='question', title=f"question from {e.get('agent')}", text=e.get('text', '')[:600]))
    k10 = sysinfo['temps'].get('k10temp')
    if k10 and k10 >= CONFIG['temp_warn']:
        attention.append(dict(level='warn', title=f'CPU at {k10:.0f} °C', text='above the usual 95 °C plateau'))
    if sysinfo['mem_avail'] < 2 << 30:
        attention.append(dict(level='error', title='RAM almost full',
                              text=f"{sysinfo['mem_avail'] / 2**30:.1f} GB available: the laptop froze from OOM before"))
    if not job_list:
        attention.append(dict(level='info', title='no optimisation running', text='the CPU is idle'))
    total = sum(f['best'] for f in files.values())
    return dict(now=int(time.time()), total=total, files=files, refs=CONFIG['leaderboard'],
                contest_end=CONFIG['contest_end'], history=score_history(files), jobs=job_list,
                system=sysinfo, agents=agents(), attention=attention, notes=notes[-50:],
                events=events[-150:], commits=commits(), cases=cases)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def local_host(self):
        # refuse requests that did not come for 127.0.0.1/localhost (DNS rebinding)
        host = (self.headers.get('Host') or '').split(':')[0]
        return host in ('127.0.0.1', 'localhost')

    def do_GET(self):
        if not self.local_host():
            return self.send(403, b'forbidden', 'text/plain')
        if self.path in ('/', '/index.html'):
            return self.send(200, read(f'{HERE}/index.html').encode(), 'text/html; charset=utf-8')
        if self.path == '/api/state':
            try:
                return self.send(200, json.dumps(state()).encode(), 'application/json')
            except Exception as e:
                return self.send(500, json.dumps(dict(error=repr(e))).encode(), 'application/json')
        self.send(404, b'not found', 'text/plain')

    def do_POST(self):
        # the custom header forces a CORS preflight, which we never answer: other websites cannot post notes
        if not self.local_host() or self.headers.get('X-Dashboard') != '1' or self.path != '/api/note':
            return self.send(403, b'forbidden', 'text/plain')
        n = int(self.headers.get('Content-Length') or 0)
        try:
            d = json.loads(self.rfile.read(min(n, 20000)))
            text = str(d['text']).strip()[:4000]
        except (ValueError, KeyError):
            return self.send(400, b'bad request', 'text/plain')
        if text:
            note = dict(id=f'n{int(time.time() * 1000)}', t=int(time.time()), who=str(d.get('who') or 'you')[:40],
                        to=str(d.get('to') or 'all')[:40], text=text)
            with open(f'{DASH}/notes.jsonl', 'a') as f:
                f.write(json.dumps(note) + '\n')
        self.send(200, b'{"ok":true}', 'application/json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=CONFIG.get('port', 8765))
    a = ap.parse_args()
    os.makedirs(DASH, exist_ok=True)
    threading.Thread(target=SAMPLER.run, daemon=True).start()
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'dashboard on http://127.0.0.1:{a.port}', flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
