"""Evaluate the real detector on a labelled dataset.

Usage (from ``backend/``):

    python scripts/evaluate_model.py --dataset D:\\datasets\\asvspoof-mini --output ../storage/eval/report

The dataset must contain one directory of spoof/synthetic files and one of
bonafide/genuine files, for example:

    dataset/
      spoof/    *.wav
      bonafide/ *.wav

Nothing is fabricated: if the dataset is missing or unreadable the script exits
non-zero and writes no metrics.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow ``python scripts/evaluate_model.py`` from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.evaluation_service import evaluate_directory, write_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the VoiceGuard AI detector.")
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Directory with spoof/ and bonafide/ sub-directories of audio files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output stem; .json and .md are written next to it.",
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--limit-per-class", type=int, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    def progress(position: int, total: int) -> None:
        if not args.quiet:
            print(f"\rscoring {position}/{total}", end="", flush=True)

    try:
        result = evaluate_directory(
            args.dataset,
            threshold=args.threshold,
            limit_per_class=args.limit_per_class,
            progress=progress,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.quiet:
        print()

    json_path, markdown_path = write_report(result, args.output)
    metrics = result.to_dict()["metrics"]
    if metrics is None:
        print(
            "error: no readable samples were evaluated, so no metrics were produced.",
            file=sys.stderr,
        )
        print(f"wrote {json_path} and {markdown_path}", file=sys.stderr)
        return 3

    print(f"samples={len(result.samples)} errors={len(result.errors)}")
    print(
        "accuracy={accuracy:.4f} precision={precision:.4f} recall={recall:.4f} "
        "f1={f1:.4f} auc={auc}".format(auc=metrics["roc_auc"], **metrics)
    )
    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
