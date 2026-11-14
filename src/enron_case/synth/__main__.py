"""python -m enron_case.synth --out DIR [--no-change] [--seed N]"""

from __future__ import annotations

import argparse
from pathlib import Path

from enron_case.synth import SynthSpec, generate


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the synthetic corpus and fixtures.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SynthSpec().seed)
    parser.add_argument("--no-change", action="store_true", help="no planted change")
    args = parser.parse_args()
    out = generate(args.out, SynthSpec(seed=args.seed, planted_change=not args.no_change))
    truth = out.truth()
    print(f"{truth['n_files']} files, {truth['n_messages']} messages -> {args.out}")


if __name__ == "__main__":
    main()
