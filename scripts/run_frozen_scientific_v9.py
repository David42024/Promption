"""Research wrapper adding supplemental integrity checks to the existing runner."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_final_scientific_v9 as runner
from scripts import scientific_evaluation as science


def supplemental(root=ROOT):
    files = list(root.glob('scripts/*holdout*.py')) + list(root.glob('scripts/run_e1_filter_holdout.py'))
    files += [root/'scripts/experimental_openai_budget_gateway.py', Path(__file__)]
    files += [p for base in ('demo', 'packages/ai-sdk') for p in (root/base).rglob('*.mjs') if 'node_modules' not in p.parts]
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files)) if p.is_file()}


def verify_supplement(folder, root=ROOT):
    p = Path(folder)/'supplementary_freeze.json'
    if hashlib.sha256(p.read_bytes()).hexdigest() != p.with_suffix('.sha256').read_text().strip():
        raise ValueError('Supplemental freeze manifest changed')
    if json.loads(p.read_text()) != supplemental(root):
        raise ValueError('Supplemental gateway/.mjs/research code changed')


def main(argv=None):
    args = runner.parse(argv)
    original = science.verify_freeze
    if args.execute:
        def verify(folder, root=ROOT):
            verify_supplement(folder, root)
            return original(folder, root)
        science.verify_freeze = verify
    try:
        code = runner.main(argv)
        if args.dry_run:
            p = args.output/'supplementary_freeze.json'
            with p.open('x', encoding='utf-8') as f:
                json.dump(supplemental(), f, indent=2)
            with p.with_suffix('.sha256').open('x') as f:
                f.write(hashlib.sha256(p.read_bytes()).hexdigest())
        if args.execute:
            verify_supplement(args.output)
        return code
    finally:
        science.verify_freeze = original


if __name__=='__main__':
    raise SystemExit(main())
