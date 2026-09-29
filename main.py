"""Avvio di QC Inspector dalla root del progetto (anche con Run in PyCharm)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from qc_inspector.main import main


if __name__ == "__main__":
    main()
