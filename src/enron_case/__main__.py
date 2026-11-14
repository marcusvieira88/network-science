"""`python -m enron_case`: the same CLI as the `enron-case` script. The one command runs its
stages this way, so a step never depends on a launcher script being on PATH."""

import sys

from enron_case.cli import main

sys.exit(main())
