"""enron-case: run the pipeline (specs/001-enron-network-analysis/contracts/cli.md).

Each stage is a function `<name>(ctx: StageContext) -> None` in `enron_case.<package>.stage`,
looked up lazily, so the orchestrator never imports a stage it does not run.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import os
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from enron_case import zones
from enron_case.config import (
    KEY_ENV,
    KEY_FILE_ENV,
    MANIFEST_FILE,
    SAMPLE_ARCHIVE,
    SAMPLE_INTERNAL_DOMAIN,
    SAMPLE_KEY_HEX,
    Config,
)
from enron_case.context import LogFn, StageContext, stderr_log
from enron_case.contracts.schemas import EXPLORATORY_CONFIDENT
from enron_case.errors import PipelineError, UsageError
from enron_case.manifest import RunManifest, code_version, file_sha256
from enron_case.zones import Paths, Zone


def _repo_root() -> Path:
    """The checkout: where this source tree lives in an editable install, else the current
    directory (the Makefile always runs from the repository root)."""
    source_root = Path(__file__).resolve().parents[2]
    return source_root if (source_root / "pyproject.toml").exists() else Path.cwd().resolve()


REPO_ROOT = _repo_root()


@dataclass(frozen=True)
class Stage:
    name: str
    package: str
    function: str


STAGES: tuple[Stage, ...] = (
    Stage("fetch", "ingest", "fetch"),
    Stage("parse", "ingest", "parse"),
    Stage("clean", "clean", "run"),
    Stage("identity", "identity", "run"),
    Stage("pseudo", "pseudo", "run"),
    Stage("network", "network", "run"),
    Stage("finding", "finding", "run"),
    Stage("risk", "risk", "run"),
    Stage("release", "release", "run"),
    Stage("report", "report", "run"),
    Stage("ui-data", "uiexport", "run"),
)
PARSE_STAGE = "parse"  # the stage that reads the archive; the manifest records its hash
DEFAULT_LAST = "report"  # ui-data runs only when asked for
KEEP_INGEST_WARNING = "warning: the ingest zone (addresses, names) stays on disk after this run"
STAGE_NAMES = tuple(s.name for s in STAGES)


def resolve(stage: Stage) -> Callable[[StageContext], object]:
    """The stage function; a stage without one is a PipelineError."""
    missing = PipelineError(f"stage '{stage.name}' is not implemented")
    try:
        module = importlib.import_module(f"enron_case.{stage.package}.stage")
    except ModuleNotFoundError as exc:
        if exc.name == f"enron_case.{stage.package}.stage":
            raise missing from exc
        raise
    fn: object = getattr(module, stage.function, None)
    if not callable(fn):
        raise missing
    return fn


def select(first: str | None, last: str | None) -> list[Stage]:
    for name in (first, last):
        if name is not None and name not in STAGE_NAMES:
            raise UsageError(f"unknown stage: {name}")
    start = STAGE_NAMES.index(first) if first else 0
    end = STAGE_NAMES.index(last or DEFAULT_LAST)
    if start > end:
        raise UsageError("--from comes after --to")
    return list(STAGES[start : end + 1])


def load_key_fingerprint(sample: bool) -> str:
    """Fingerprint of the run key; raise KeyProblem if it is unavailable or unfit for the run."""
    # Imported here: pseudo.keys imports REPO_ROOT from this module.
    from enron_case.pseudo.keys import key_fingerprint, load_run_key  # noqa: PLC0415

    return key_fingerprint(load_run_key(sample))


def ensure_sample_corpus(paths: Paths) -> None:
    from enron_case.synth import generate  # noqa: PLC0415 - only sample runs need it

    if not (paths.dir(Zone.RAW) / SAMPLE_ARCHIVE).exists():
        generate(paths.data_root)


@dataclass
class RunResult:
    manifest: RunManifest
    ran: list[str]


def run_pipeline(
    paths: Paths,
    config: Config,
    sample: bool,
    stages: Sequence[Stage],
    keep_ingest: bool = False,
    log: LogFn = stderr_log,
) -> RunResult:
    """Run `stages` in order and write the run manifest to the release zone. A stage without
    a stage function is a PipelineError."""
    manifest = RunManifest(
        parameters=config.as_record(),
        seed=config.seed,
        sample=sample,
        code_version=code_version(REPO_ROOT),
    )
    if sample:
        ensure_sample_corpus(paths)
        manifest.corpus_sha256 = file_sha256(paths.dir(Zone.RAW) / SAMPLE_ARCHIVE)
    ran: list[str] = []
    try:
        for stage in stages:
            if sample and stage.name == "fetch":
                continue
            fn = resolve(stage)
            if stage.package == "pseudo":
                manifest.key_fingerprint = load_key_fingerprint(sample)
            ctx = StageContext(stage.package, config, paths, sample, log)
            started = time.perf_counter()
            fn(ctx)
            seconds = time.perf_counter() - started
            manifest.tables.update(ctx.outputs)
            manifest.counts.update(ctx.count_outputs)
            manifest.corpus_sha256 = ctx.corpus_sha256 or manifest.corpus_sha256
            manifest.record_stage(stage.name, seconds)
            ran.append(stage.name)
            log(f"[{stage.name}] done in {seconds:.1f}s")
    finally:
        if not keep_ingest:
            zones.purge_ingest(paths)
    full_run = bool(stages) and stages[0].name in {"fetch", PARSE_STAGE}
    target = zones.path_for(paths, "cli", Zone.RELEASE, MANIFEST_FILE, "w")
    manifest.write(target, merge=not full_run)
    return RunResult(manifest, ran)


def verify(config: Config, log: LogFn) -> int:
    """Run the sample twice in separate directories and compare analytical fingerprints."""
    prints = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in (1, 2):
            root = Path(tmp) / f"run{i}"
            paths = Paths(root / "data", root / "release", root / "ui", root / "docs")
            result = run_pipeline(paths, config, True, select(None, None), log=log)
            prints.append(result.manifest.analytical_fingerprints())
    differ = sorted(
        k for k in prints[0].keys() | prints[1].keys() if prints[0].get(k) != prints[1].get(k)
    )
    if differ:
        log(f"verify: {len(differ)} outputs differ: {', '.join(differ)}")
        return 1
    log(f"verify: {len(prints[0])} outputs identical across two runs")
    return 0


def summary_line(release_root: Path) -> str:
    """How many hypotheses the release holds true, counted as the explorer counts them: the
    headline among the preregistered ones, every confident outcome among the exploratory ones."""
    tables = [release_root / "hypotheses.csv", release_root / "exploratory.csv"]
    if not all(table.is_file() for table in tables):
        raise PipelineError(f"no release tables in {release_root.name}/; run the pipeline first")
    hypotheses = pl.read_csv(tables[0], schema_overrides={"is_headline": pl.Boolean})
    exploratory = pl.read_csv(tables[1])
    held_true = (
        hypotheses.filter(pl.col("is_headline")).height
        + exploratory.filter(pl.col("outcome") == EXPLORATORY_CONFIDENT).height
    )
    total = hypotheses.height + exploratory.height
    return f"{held_true} of {total} hypotheses held true"


def _parse_sets(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep:
            raise UsageError(f"--set expects NAME=VALUE, got {item}")
        out[name] = value
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enron-case")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a range of stages (default: all through report)")
    run.add_argument("--sample", action="store_true")
    run.add_argument("--from", dest="first", choices=STAGE_NAMES)
    run.add_argument("--to", dest="last", choices=STAGE_NAMES)
    run.add_argument("--keep-ingest", action="store_true")
    run.add_argument("--set", dest="sets", action="append", default=[], metavar="NAME=VALUE")
    stage = sub.add_parser("stage", help="run one stage")
    stage.add_argument("name", choices=STAGE_NAMES)
    stage.add_argument("--sample", action="store_true")
    stage.add_argument("--keep-ingest", action="store_true")
    stage.add_argument("--set", dest="sets", action="append", default=[], metavar="NAME=VALUE")
    sub.add_parser("verify", help="double-run determinism check on the sample")
    sub.add_parser("check-key", help="exit 0 if a usable key is configured, else 3")
    summary = sub.add_parser("summary", help="print how many hypotheses the release holds true")
    summary.add_argument("--sample", action="store_true")
    sub.add_parser(
        "review-merges",
        help="T046: judge a seeded sample of identity merges in this terminal (counts only kept)",
    )
    for name, text in ONE_COMMAND_HELP.items():
        sub.add_parser(name, help=text)
    return parser


INFO_COMMANDS = ("check-key", "review-merges", "summary")
# The one command and its helpers (enron_case.onecommand); the same on every OS.
ONE_COMMAND_HELP = {
    "all": "the one command: every step, then serve the explorer until Ctrl+C",
    "check": "every step of `all` except serving the explorer",
    "gate": "Python gate: lint, format, strict types, all tests",
    "ui-gate": "UI gate: install UI dependencies if needed, lint, types, tests, build, check",
    "ui-deps": "install the UI dependencies if the lockfile is newer than the installed tree",
    "key": "create a key outside the repository if none exists (KEY_FILE, else the default)",
}


def _run_one_command(command: str) -> int:
    from enron_case import onecommand  # noqa: PLC0415 - it imports this module

    if command in onecommand.MODES:
        return onecommand.run_one_command(command)
    return onecommand.run_helper(command)


def _run_info_command(args: argparse.Namespace) -> None:
    """Commands that run no pipeline stage; each raises a PipelineError on failure."""
    if args.command == "check-key":
        load_key_fingerprint(sample=False)
    elif args.command == "review-merges":
        from enron_case.identity.review import review  # noqa: PLC0415 - this command only

        ctx = StageContext("identity", Config(), Paths.for_run(REPO_ROOT, False), False)
        checked, correct = review(ctx)
        stderr_log(f"review-merges: {correct} of {checked} merges judged correct")
    else:
        print(summary_line(Paths.for_run(REPO_ROOT, args.sample).release_root))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "sample", False) or args.command == "verify":
        os.environ[KEY_ENV] = SAMPLE_KEY_HEX
        os.environ.pop(KEY_FILE_ENV, None)
    try:
        if args.command in ONE_COMMAND_HELP:
            return _run_one_command(args.command)
        if args.command in INFO_COMMANDS:
            _run_info_command(args)
            return 0
        config = Config()
        if args.command == "verify":
            sample_config = dataclasses.replace(config, internal_domain=SAMPLE_INTERNAL_DOMAIN)
            return verify(sample_config, stderr_log)
        if args.sample:
            config = dataclasses.replace(config, internal_domain=SAMPLE_INTERNAL_DOMAIN)
        config = config.with_overrides(_parse_sets(args.sets))
        if args.command == "run":
            stages = select(args.first, args.last)
            if args.keep_ingest:
                stderr_log(KEEP_INGEST_WARNING)
        else:
            stages = select(args.name, args.name)
        paths = Paths.for_run(REPO_ROOT, args.sample)
        keep = args.keep_ingest or args.command == "stage"
        if args.command == "stage":
            stderr_log(KEEP_INGEST_WARNING)
        run_pipeline(paths, config, args.sample, stages, keep_ingest=keep)
        print(paths.release_root / "report.md")
        return 0
    except PipelineError as exc:
        stderr_log(f"error: {exc}")
        return exc.exit_code
    except Exception as exc:
        stderr_log(f"error: unexpected {type(exc).__name__}; details withheld (may hold data)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
