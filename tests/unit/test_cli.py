"""Stage lookup: every stage has a function; a stage without one is an error, not a skip."""

from __future__ import annotations

from pathlib import Path

import pytest

from enron_case.cli import STAGES, Stage, resolve, run_pipeline
from enron_case.config import Config
from enron_case.errors import PipelineError
from helpers import tmp_paths

# `contracts` is a package with no stage module.
GHOST = Stage("ghost", "contracts", "run")


@pytest.mark.parametrize("stage", STAGES, ids=lambda stage: stage.name)
def test_every_stage_resolves_to_a_function(stage: Stage) -> None:
    assert callable(resolve(stage))


def test_stage_without_a_stage_module_is_an_error() -> None:
    with pytest.raises(PipelineError, match="'ghost' is not implemented"):
        resolve(GHOST)


def test_stage_without_its_function_is_an_error() -> None:
    with pytest.raises(PipelineError, match="'parse' is not implemented"):
        resolve(Stage("parse", "ingest", "no_such_function"))


def test_run_fails_at_a_missing_stage(tmp_path: Path) -> None:
    paths = tmp_paths(tmp_path)
    with pytest.raises(PipelineError, match="'ghost' is not implemented"):
        run_pipeline(paths, Config(), sample=False, stages=[GHOST], log=lambda _: None)
