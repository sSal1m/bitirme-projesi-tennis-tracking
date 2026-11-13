"""Final comparison table: RF-DETR vs HSV on one reviewed reference.

The evaluation measures *automatic* output against a *reviewed* reference. To
compare two detectors fairly, both must be scored against the same reference.
This script therefore:

1. Takes the reviewed session as the reference (every included shot reviewed).
2. Copies that reference into the other session - the automatic output of each
   session is untouched.
3. Scores both and prints one table.

Nothing stored is modified: the borrowed reference is written to a separate
file next to the other session, and the reviewed session is left alone.

Usage:
    python scripts/compare_sessions.py --reference data/<REVIEWED_ID> \
                                       --other data/<OTHER_ID>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tennis_tracking.domain import Session, Shot
from tennis_tracking.evaluation import evaluate

ROOT = Path(__file__).resolve().parents[1]


def load_session(reference: str) -> tuple[Path, Session]:
    path = Path(reference)
    if path.is_dir():
        path = path / "session.json"
    if not path.is_file():
        raise SystemExit(f"Oturum dosyasi bulunamadi: {path}")
    return path, Session.from_dict(json.loads(path.read_text("utf-8")))


def borrow_reference(reference: Session, other: Session) -> Session:
    """Give the other session the reviewed shot list, keeping its own automatic output."""
    borrowed = Session.from_dict(other.to_dict())
    borrowed.shots = [
        Shot(
            contact_t=shot.contact_t,
            wall_t=shot.wall_t,
            wall_xy=list(shot.wall_xy) if shot.wall_xy else None,
            kind=shot.kind,
            confidence=shot.confidence,
            source=shot.source,
            reviewed=True,
            included=shot.included,
            id=shot.id,
        )
        for shot in reference.shots
        if shot.included
    ]
    borrowed.automatic_shots = other.automatic_shots
    return borrowed


def label_for(session: Session) -> str:
    return "RF-DETR" if session.detector == "rfdetr" else "HSV"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, help="Elle incelenmis oturum.")
    parser.add_argument("--other", required=True, help="Karsilastirilacak diger oturum.")
    parser.add_argument("--tolerance", type=float, default=0.08)
    parser.add_argument(
        "--write", action="store_true", help="Turetilmis oturumu dosyaya da yaz."
    )
    args = parser.parse_args()

    reference_path, reference = load_session(args.reference)
    other_path, other = load_session(args.other)

    if Path(reference.video_path).resolve() != Path(other.video_path).resolve():
        raise SystemExit(
            "Iki oturum ayni videoyu analiz etmiyor; karsilastirma anlamli olmaz.\n"
            f"  referans: {reference.video_path}\n  diger   : {other.video_path}"
        )

    included = [s for s in reference.shots if s.included]
    pending = [s for s in included if not s.reviewed]
    if pending:
        raise SystemExit(
            f"Referansta {len(pending)} vurus incelenmemis. Once inceleme sekmesinde "
            "hepsini 'Incelendi · kaydet' ile kaydet."
        )

    borrowed = borrow_reference(reference, other)
    if args.write:
        target = other_path.with_name("session.with-reference.json")
        target.write_text(
            json.dumps(borrowed.to_dict(), ensure_ascii=False, indent=2, allow_nan=False), "utf-8"
        )
        print(f"Turetilmis oturum yazildi: {target}")

    results = {
        label_for(reference): evaluate(reference, args.tolerance),
        label_for(other): evaluate(borrowed, args.tolerance),
    }

    print()
    print("=" * 88)
    print("Vurus karsilastirmasi - ayni elle incelenmis referans")
    print(f"Video: {Path(reference.video_path).name} | tolerans: +/-{args.tolerance * 1000:.0f} ms")
    print(f"Referans vurus sayisi: {len(included)}")
    print("=" * 88)

    header = (
        f"{'Yontem':<10}{'Raket temas P':>15}{'R':>8}{'F1':>8}"
        f"{'Duv. temas P':>14}{'R':>8}{'F1':>8}{'Sinif.':>10}{'Yerlesme':>11}"
    )
    print(header)
    print("-" * len(header))
    for label, result in results.items():
        racket = result["racket_contacts"]
        wall = result["wall_contacts"]
        coverage = result["classification_coverage"]
        placement = result["placement_mean_normalized_error"]
        print(
            f"{label:<10}"
            f"{racket['precision'] * 100:>14.1f}%{racket['recall'] * 100:>7.1f}%{racket['f1'] * 100:>7.1f}%"
            f"{wall['precision'] * 100:>13.1f}%{wall['recall'] * 100:>7.1f}%{wall['f1'] * 100:>7.1f}%"
            f"{(coverage * 100 if coverage is not None else 0):>9.1f}%"
            f"{(placement if placement is not None else 0):>11.4f}"
        )

    print("-" * len(header))
    print("Siniflandirma dogrulugu (yalnizca siniflandirilanlar):")
    for label, result in results.items():
        accuracy = result["classification_accuracy"]
        print(
            f"  {label:<10}"
            f"{accuracy * 100:>6.1f}%"
            f"   (kapsam {(result['classification_coverage'] or 0) * 100:.1f}%)"
        )
    print()
    print("Hiz her zaman dogrulanmamis olarak isaretlenir (speed_validated=false).")
    print("Bu tablo gecmis bir oturumun uzerinde olculdu; genellenebilirlik kaniti degildir.")

    output = ROOT / "data" / "session_comparison.json"
    output.write_text(
        json.dumps(
            {
                "video": reference.video_path,
                "tolerance_seconds": args.tolerance,
                "reference_strokes": len(included),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        "utf-8",
    )
    print(f"\nRapor yazildi: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
