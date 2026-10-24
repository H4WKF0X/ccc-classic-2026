"""Overnight optimisation of 3-large: everything we learned, in rounds.

Each round (default 45 min):
  1. Open cases = large cases whose best is above the proven lower bound (results/level6/bounds.csv),
     sorted by gap.  Proven-optimal cases are skipped.
  2. In parallel:
     * the fast Rust beam optimiser (seeded from the current best, symmetries, wide beams) on a reduced
       input that contains only the open cases;
     * the exact window re-optimiser (tools/level6/improve.py, CP-SAT between two copies) on the open
       cases, shortest programs first (big patterns are out of reach for the exact solver).
  3. Merge: Rust output and every improved window go into work/level6/candidates/, then
     `cargo ccc best 6` keeps the shortest valid program per case in work/level6/best/.
Everything is on disk after every round (and improve.py writes each win immediately), so a crash or
reboot loses at most the current Rust round; just start the script again.

usage (from the repo root):
  nice -n 10 ~/.ccc-venv/bin/python -u tools/level6/overnight_large.py --hours 8
Progress: work/level6/overnight/progress.log (one line per round with totals).
"""
import argparse, csv, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L6 = os.path.join(ROOT, 'work', 'level6')
TOOLS = os.path.join(ROOT, 'tools', 'level6')
RES = os.path.join(ROOT, 'results', 'level6')
KEY = '3-large'
PY = os.path.expanduser('~/.ccc-venv/bin/python')


def read_cases():
    """Raw text blocks of every case (header + grid lines) of the large input."""
    lines = [l for l in open(f'{L6}/in/in_level-6_{KEY}.txt').read().split('\n') if l.strip()]
    n = int(lines[0]); i = 1; blocks = []
    for _ in range(n):
        rows = int(lines[i].split()[1]); blocks.append(lines[i:i + 1 + rows]); i += 1 + rows
    return blocks


def read_best():
    return open(f'{L6}/best/out_level-6_{KEY}.txt').read().strip('\n').split('\n\n')


def lower_bounds():
    lb = {}
    for r in csv.DictReader(open(f'{RES}/bounds.csv')):
        if r['file'] == KEY and r['lb']:
            lb[int(r['case'])] = int(r['lb'])
    return lb


def total(progs):
    return sum(len(p.split('\n')) for p in progs)


def write_full(progs, path):
    open(path, 'w').write('\n\n'.join(p.strip('\n') for p in progs) + '\n\n')


def merge(log):
    out = subprocess.run(['cargo', 'ccc', 'best', '6'], cwd=ROOT, capture_output=True, text=True).stdout
    for l in out.split('\n'):
        if KEY in l:
            log(l.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours', type=float, default=8)
    ap.add_argument('--round-min', type=float, default=45)
    ap.add_argument('--rust-threads', type=int, default=8)
    ap.add_argument('--cpsat-workers', type=int, default=4)
    a = ap.parse_args()
    od = f'{L6}/overnight'; os.makedirs(od, exist_ok=True)
    logf = open(f'{od}/progress.log', 'a')

    def log(msg):
        line = f'[{time.strftime("%H:%M:%S")}] {msg}'
        print(line, flush=True); logf.write(line + '\n'); logf.flush()

    end = time.time() + a.hours * 3600
    blocks = read_cases()
    rnd = 0
    while time.time() < end - 300:
        rnd += 1
        best = read_best(); lb = lower_bounds()
        open_cases = sorted((i for i in range(len(best)) if len(best[i].split('\n')) > lb.get(i, 0)),
                            key=lambda i: -(len(best[i].split('\n')) - lb.get(i, 0)))
        gap = sum(len(best[i].split('\n')) - lb.get(i, 0) for i in open_cases)
        log(f'round {rnd}: large best {total(best)}, {len(open_cases)} open cases, gap to bounds {gap}')
        if not open_cases:
            break
        secs = int(min(a.round_min * 60, end - time.time() - 120))
        # reduced input + matching seed file for the Rust optimiser
        rin = f'{od}/in_open.txt'; seed_dir = f'{od}/seed'; os.makedirs(seed_dir, exist_ok=True)
        with open(rin, 'w') as f:
            f.write(f'{len(open_cases)}\n')
            for i in open_cases:
                f.write('\n'.join(blocks[i]) + '\n\n')
        write_full([best[i] for i in open_cases], f'{seed_dir}/out_open.txt')
        rout = f'{od}/out_open_r{rnd}.txt'
        env = dict(os.environ, L6_SEED_DIR=seed_dir, CCC_THREADS=str(a.rust_threads), L6_SEED=str(rnd))
        rust = subprocess.Popen(['nice', '-n', '10', 'cargo', 'ccc', 'run', '6', rin, rout, '--budget', str(secs)],
                                cwd=ROOT, env=env, stdout=open(f'{od}/rust_r{rnd}.log', 'w'), stderr=subprocess.STDOUT)
        cp = subprocess.Popen(['nice', '-n', '10', 'timeout', str(secs), PY, '-u', f'{TOOLS}/improve.py', KEY,
                               '--cases', ','.join(map(str, sorted(open_cases, key=lambda i: len(best[i].split('\n'))))),
                               '--maxlen', '30', '--secs', '60',
                               '--workers', str(a.cpsat_workers)],
                              cwd=TOOLS, stdout=open(f'{od}/improve_r{rnd}.log', 'w'), stderr=subprocess.STDOUT)
        rust.wait(); cp.wait()
        # map the Rust programs back into a full large file
        if os.path.exists(rout):
            rprogs = open(rout).read().strip('\n').split('\n\n')
            if len(rprogs) == len(open_cases):
                full = read_best()
                for j, i in enumerate(open_cases):
                    if len(rprogs[j].split('\n')) < len(full[i].split('\n')):
                        full[i] = rprogs[j]
                write_full(full, f'{L6}/candidates/overnight_rust_r{rnd}_{KEY}.txt')
        # improved windows (single programs) -> full file
        full = read_best(); imp = 0
        idir = f'{RES}/improved'
        for name in os.listdir(idir) if os.path.isdir(idir) else []:
            if name.startswith(KEY + '_'):
                i = int(name[len(KEY) + 1:-4]); p = open(f'{idir}/{name}').read().strip('\n')
                if len(p.split('\n')) < len(full[i].split('\n')):
                    full[i] = p; imp += 1
        if imp:
            write_full(full, f'{L6}/candidates/overnight_cpsat_r{rnd}_{KEY}.txt')
        merge(log)
        log(f'round {rnd} done: large best {total(read_best())}')
    log('overnight run finished')


if __name__ == '__main__':
    main()
