"""Merge exact window wins (results/level6/improved/<key>_<case>.txt) into work/level6/best/.

Builds one full candidate file per input from the current best plus every shorter improved program,
then runs `cargo ccc best 6`, which re-checks everything and keeps the shortest valid program per case.
usage (from anywhere): ~/.ccc-venv/bin/python tools/level6/merge_improved.py [4-enormous ...]
"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import overnight_large as o

keys = sys.argv[1:] or ['2-medium', '3-large', '4-enormous']
for key in keys:
    o.KEY = key
    full = o.read_best(); imp = []
    for name in sorted(os.listdir(f'{o.RES}/improved')):
        if name.startswith(key + '_') and name[len(key) + 1:-4].isdigit():
            i = int(name[len(key) + 1:-4]); p = open(f'{o.RES}/improved/{name}').read().strip('\n')
            if len(p.split('\n')) < len(full[i].split('\n')):
                full[i] = p; imp.append(i)
    print(key, 'improved cases:', imp or 'none')
    if imp:
        o.write_full(full, f'{o.L6}/candidates/improved_{key}.txt')
out = subprocess.run(['cargo', 'ccc', 'best', '6'], cwd=o.ROOT, capture_output=True, text=True).stdout
print('\n'.join(l for l in out.split('\n') if 'out_level-6' in l))
