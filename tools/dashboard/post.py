"""Post to the dashboard (work/dashboard/events.jsonl), or read the human's notes.

  python3 tools/dashboard/post.py --agent satmodel2 --kind win "medium case 186 proven optimal (26)"
  python3 tools/dashboard/post.py --agent satmodel2 --kind question "run 167 with 8 threads overnight?"
  python3 tools/dashboard/post.py --notes                 # notes from the human that nobody answered yet
  python3 tools/dashboard/post.py --agent main --ack n1761... "done, started it"   # answer a note

kinds: info (progress), win (shorter program / new proof), question (needs the human), done, error, plan.
"""
import argparse, json, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASH = f'{ROOT}/work/dashboard'


def load(path):
    try:
        return [json.loads(l) for l in open(path) if l.strip()]
    except OSError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('text', nargs='?', default='')
    ap.add_argument('--agent', default='main')
    ap.add_argument('--kind', default='info', choices=['info', 'win', 'question', 'done', 'error', 'plan'])
    ap.add_argument('--ack', help='id of the note or question this answers')
    ap.add_argument('--notes', action='store_true', help='print unanswered notes from the human')
    a = ap.parse_args()
    os.makedirs(DASH, exist_ok=True)
    if a.notes:
        acked = {e.get('ack') for e in load(f'{DASH}/events.jsonl')}
        for n in load(f'{DASH}/notes.jsonl'):
            if n['id'] not in acked:
                print(f"{n['id']}  to {n.get('to', 'all')}: {n['text']}")
        return
    if not a.text and not a.ack:
        ap.error('nothing to post')
    ev = dict(id=f'e{int(time.time() * 1000)}', t=int(time.time()), agent=a.agent, kind=a.kind, text=a.text)
    if a.ack:
        ev['ack'] = a.ack
    with open(f'{DASH}/events.jsonl', 'a') as f:
        f.write(json.dumps(ev) + '\n')


if __name__ == '__main__':
    main()
