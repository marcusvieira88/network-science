"""`enron-case` dispatch (cli.main): which stages run, what is kept and what is printed. The
pipeline, key and review functions are replaced, so no stage, key or corpus is touched."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from enron_case import cli
from enron_case.config import (
    HYPOTHESES_STATED,
    KEY_ENV,
    KEY_FILE_ENV,
    SAMPLE_INTERNAL_DOMAIN,
    SAMPLE_KEY_HEX,
    Config,
)
from enron_case.context import LogFn, StageContext, stderr_log
from enron_case.contracts.schemas import DEPARTURE_PRIMARY, EXPLORATORY_CONFIDENT
from enron_case.errors import KeyProblem
from enron_case.manifest import RunManifest
from enron_case.zones import Paths

LEAKY_ADDRESS = "someone@example.invalid"
NOT_THE_SAMPLE_KEY = "0" * len(SAMPLE_KEY_HEX)


@dataclass
class PipelineCall:
    paths: Paths
    config: Config
    sample: bool
    stages: list[str]
    keep_ingest: bool


@dataclass
class FakePipeline:
    """Stands in for run_pipeline: records each call and returns fixed fingerprints."""

    fingerprints: list[dict[str, str]] = field(default_factory=list)
    calls: list[PipelineCall] = field(default_factory=list)

    def __call__(
        self,
        paths: Paths,
        config: Config,
        sample: bool,
        stages: Sequence[cli.Stage],
        keep_ingest: bool = False,
        log: LogFn = stderr_log,
    ) -> cli.RunResult:
        self.calls.append(
            PipelineCall(paths, config, sample, [s.name for s in stages], keep_ingest)
        )
        manifest = RunManifest(parameters={}, seed=config.seed, sample=sample, code_version="t")
        if self.fingerprints:
            manifest.tables = self.fingerprints[len(self.calls) - 1]
        return cli.RunResult(manifest, [s.name for s in stages])


@pytest.fixture
def pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakePipeline:
    """The repository root moved to tmp_path, the key environment restored after the test
    (main sets the sample key) and run_pipeline replaced by a recorder."""
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    # Not the sample key, so a test can tell that main() switched to it.
    monkeypatch.setenv(KEY_ENV, NOT_THE_SAMPLE_KEY)
    monkeypatch.setenv(KEY_FILE_ENV, str(tmp_path / "unused.key"))
    fake = FakePipeline()
    monkeypatch.setattr(cli, "run_pipeline", fake)
    return fake


def test_run_with_a_stage_range_and_keep_ingest_warns(
    pipeline: FakePipeline, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["run", "--sample", "--from", "network", "--to", "release", "--keep-ingest"])
    out, err = capsys.readouterr()
    assert code == 0
    [call] = pipeline.calls
    assert call.stages == ["network", "finding", "risk", "release"]
    assert call.keep_ingest is True
    assert call.sample is True
    assert call.config.internal_domain == SAMPLE_INTERNAL_DOMAIN
    assert call.paths == Paths.for_run(tmp_path, True)
    assert err == cli.KEEP_INGEST_WARNING + "\n"
    assert out == f"{tmp_path / 'release-sample' / 'report.md'}\n"


def test_sample_run_uses_the_sample_key_and_no_key_file(pipeline: FakePipeline) -> None:
    assert cli.main(["run", "--sample"]) == 0
    assert os.environ[KEY_ENV] == SAMPLE_KEY_HEX
    assert KEY_FILE_ENV not in os.environ


def test_run_without_keep_ingest_purges_and_does_not_warn(
    pipeline: FakePipeline, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run", "--sample"]) == 0
    [call] = pipeline.calls
    assert call.stages == [
        "fetch",
        "parse",
        "clean",
        "identity",
        "pseudo",
        "network",
        "finding",
        "risk",
        "release",
        "report",
    ]
    assert call.keep_ingest is False
    assert capsys.readouterr().err == ""


def test_stage_runs_one_stage_keeps_ingest_and_warns(
    pipeline: FakePipeline, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["stage", "pseudo", "--sample"]) == 0
    [call] = pipeline.calls
    assert call.stages == ["pseudo"]
    assert call.keep_ingest is True
    assert capsys.readouterr().err == cli.KEEP_INGEST_WARNING + "\n"


def test_stage_without_sample_uses_the_real_zones_and_domain(
    pipeline: FakePipeline, tmp_path: Path
) -> None:
    assert cli.main(["stage", "network"]) == 0
    [call] = pipeline.calls
    assert call.sample is False
    assert call.config.internal_domain == Config().internal_domain
    assert call.paths == Paths.for_run(tmp_path, False)


def test_set_overrides_reach_the_pipeline_config(pipeline: FakePipeline) -> None:
    code = cli.main(
        [
            "run",
            "--sample",
            "--set",
            "alpha=0.01",
            "--set",
            "baseline_end=2000-06-30",
            "--set",
            "degree_bucket_floors=1,4",
        ]
    )
    assert code == 0
    config = pipeline.calls[0].config
    assert config.alpha == 0.01
    assert config.baseline_end.isoformat() == "2000-06-30"
    assert config.degree_bucket_floors == (1, 4)


@pytest.mark.parametrize(
    ("setting", "message"),
    [
        ("alpha", "error: --set expects NAME=VALUE, got alpha\n"),
        ("no_such_parameter=1", "error: unknown parameter: no_such_parameter\n"),
        ("baseline_end=June", "error: bad value for parameter baseline_end\n"),
    ],
)
def test_bad_set_is_a_usage_error(
    pipeline: FakePipeline, capsys: pytest.CaptureFixture[str], setting: str, message: str
) -> None:
    assert cli.main(["run", "--sample", "--set", setting]) == 2
    assert capsys.readouterr().err == message
    assert pipeline.calls == []


def test_unexpected_error_withholds_its_message(
    pipeline: FakePipeline, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An exception that is not a PipelineError may carry data in its message: only its type
    is logged, and the exit code is 1."""

    def leaky(*_args: object, **_kwargs: object) -> cli.RunResult:
        raise RuntimeError(f"could not handle {LEAKY_ADDRESS}")

    monkeypatch.setattr(cli, "run_pipeline", leaky)
    code = cli.main(["run", "--sample"])
    out, err = capsys.readouterr()
    assert code == 1
    assert out == ""
    assert err == "error: unexpected RuntimeError; details withheld (may hold data)\n"
    assert "@" not in out + err


def test_verify_compares_two_sample_runs(
    pipeline: FakePipeline, capsys: pytest.CaptureFixture[str]
) -> None:
    pipeline.fingerprints = [{"a.csv": "1", "b.csv": "2"}, {"a.csv": "1", "b.csv": "2"}]
    assert cli.main(["verify"]) == 0
    assert capsys.readouterr().err == "verify: 2 outputs identical across two runs\n"
    assert [c.sample for c in pipeline.calls] == [True, True]
    assert {c.config.internal_domain for c in pipeline.calls} == {SAMPLE_INTERNAL_DOMAIN}
    assert pipeline.calls[0].paths.data_root != pipeline.calls[1].paths.data_root


def test_verify_names_the_outputs_that_differ(pipeline: FakePipeline) -> None:
    """b.csv changes and c.csv appears only in the second run: two outputs differ."""
    pipeline.fingerprints = [
        {"a.csv": "1", "b.csv": "2"},
        {"a.csv": "1", "b.csv": "3", "c.csv": "4"},
    ]
    logged: list[str] = []
    assert cli.verify(Config(), logged.append) == 1
    assert logged == ["verify: 2 outputs differ: b.csv, c.csv"]


def test_check_key_reports_success_and_a_key_problem(
    pipeline: FakePipeline, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[bool] = []

    def usable(sample: bool) -> str:
        asked.append(sample)
        return "fingerprint"

    monkeypatch.setattr(cli, "load_key_fingerprint", usable)
    assert cli.main(["check-key"]) == 0
    assert asked == [False]

    def missing(sample: bool) -> str:
        raise KeyProblem("no key configured")

    monkeypatch.setattr(cli, "load_key_fingerprint", missing)
    assert cli.main(["check-key"]) == 3
    assert capsys.readouterr().err == "error: no key configured\n"


def test_review_merges_reports_counts_only(
    pipeline: FakePipeline,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contexts: list[StageContext] = []

    def judged(ctx: StageContext) -> tuple[int, int]:
        contexts.append(ctx)
        return 4, 3

    monkeypatch.setattr("enron_case.identity.review.review", judged)
    assert cli.main(["review-merges"]) == 0
    assert capsys.readouterr().err == "review-merges: 3 of 4 merges judged correct\n"
    [ctx] = contexts
    assert (ctx.package, ctx.sample) == ("identity", False)
    assert ctx.paths == Paths.for_run(tmp_path, False)


def _summary_release(tmp_path: Path, departure_outcome: str) -> None:
    """One headline of two preregistered hypotheses, one confident of two exploratory ones, and
    H26 with the given outcome on its primary variant (the other variants carry none)."""
    release = tmp_path / "release-sample"
    release.mkdir()
    (release / "hypotheses.csv").write_text("hypothesis,is_headline\nH1,true\nH2,false\n")
    (release / "exploratory.csv").write_text(
        f"hypothesis,outcome\nH5,{EXPLORATORY_CONFIDENT}\nH6,not supported\n"
    )
    (release / "departure_tests.csv").write_text(
        f"variant,outcome\n{DEPARTURE_PRIMARY},{departure_outcome}\nsilence 8,\n"
    )


def test_summary_counts_h26_among_the_hypotheses(
    pipeline: FakePipeline, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """H26 not established: five hypotheses, two held true."""
    _summary_release(tmp_path, "not established")
    assert cli.main(["summary", "--sample"]) == 0
    assert capsys.readouterr().out == "2 of 5 hypotheses held true\n"


@pytest.mark.parametrize(("outcome", "held"), [("high", 3), ("moderate", 3), ("low", 2)])
def test_summary_holds_h26_true_only_as_a_finding(
    outcome: str,
    held: int,
    pipeline: FakePipeline,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """High or moderate confidence is a finding, as in the explorer; low is a lead."""
    _summary_release(tmp_path, outcome)
    assert cli.main(["summary", "--sample"]) == 0
    assert capsys.readouterr().out == f"{held} of 5 hypotheses held true\n"


def test_summary_on_the_committed_release_counts_all_stated_hypotheses() -> None:
    """The committed release holds every stated hypothesis, H26 included, and none is held."""
    release = Path(__file__).resolve().parents[2] / "release"
    assert cli.summary_line(release) == f"0 of {HYPOTHESES_STATED} hypotheses held true"


def test_summary_without_a_release_fails(
    pipeline: FakePipeline, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["summary"]) == 1
    assert (
        capsys.readouterr().err == "error: no release tables in release/; run the pipeline first\n"
    )


def test_helper_commands_reach_the_one_command_module(
    pipeline: FakePipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    helpers: list[str] = []

    def helper(command: str) -> int:
        helpers.append(command)
        return 0

    monkeypatch.setattr("enron_case.onecommand.run_helper", helper)
    assert cli.main(["key"]) == 0
    assert helpers == ["key"]
