"""Write one case + its best program as two files for the offline viewer
(work/level6/statement/sandbox-level-6.html: drag <..>_input.txt onto "Input", <..>_solution.txt onto "Solution").
usage: python3 tools/level6/view_case.py <2-medium|3-large|4-enormous> <case>   (or 'longest')"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L6 = os.path.join(ROOT, 'work', 'level6')
key, which = sys.argv[1], sys.argv[2]
L = [l.rstrip('\n') for l in open(f'{L6}/in/in_level-6_{key}.txt')]
L = [l for l in L if l.strip()]
n = int(L[0]); i = 1; cases = []
for _ in range(n):
    rows = int(L[i].split()[1]); cases.append(L[i:i + 1 + rows]); i += 1 + rows
progs = open(f'{L6}/best/out_level-6_{key}.txt').read().strip('\n').split('\n\n')
k = max(range(n), key=lambda j: len(progs[j].split('\n'))) if which == 'longest' else int(which)
out = f'{L6}/view'; os.makedirs(out, exist_ok=True)
base = f'{out}/{key}_case{k:03d}'
open(base + '_input.txt', 'w').write('\n'.join(cases[k]) + '\n')
open(base + '_solution.txt', 'w').write(progs[k].strip('\n') + '\n')
print(f'case {k}: R={cases[k][0].split()[0]}, count={cases[k][0].split()[3]}, {len(progs[k].split(chr(10)))} lines')
print(base + '_input.txt'); print(base + '_solution.txt')
