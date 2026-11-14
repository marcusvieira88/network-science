from __future__ import annotations

import os
from pathlib import Path

import pytest

from enron_case.synth import SynthOutput, SynthSpec, generate
from helpers import TEST_KEY_HEX

os.environ.setdefault("ENRON_CASE_KEY", TEST_KEY_HEX)


@pytest.fixture(scope="session")
def synth(tmp_path_factory: pytest.TempPathFactory) -> SynthOutput:
    """Synthetic corpus with a planted change, its ground truth and all contract fixtures."""
    return generate(tmp_path_factory.mktemp("synth"))


@pytest.fixture(scope="session")
def synth_nochange(tmp_path_factory: pytest.TempPathFactory) -> SynthOutput:
    """Same organisation and noise, no planted change."""
    return generate(tmp_path_factory.mktemp("synth_nochange"), SynthSpec(planted_change=False))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path
