from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_classifier_enrichment_v1_benchmark_passes_release_thresholds():
    backend_dir = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(backend_dir / "benchmarks" / "classifier_enrichment_v1.py"),
            "--json",
        ],
        cwd=backend_dir,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    metrics = json.loads(completed.stdout)
    assert metrics["passed"] is True
    assert metrics["case_count"] >= 20
    assert metrics["partition_count"] >= 20
    assert metrics["semantic_accuracy"] > metrics["baseline_semantic_accuracy"]
    assert metrics["merchant_auto_precision"] == 1.0
    assert metrics["relationship_precision"] == 1.0
    assert metrics["relationship_recall"] == 1.0
