import argparse
import json
from pathlib import Path

from tennis_tracking.domain import Session
from tennis_tracking.evaluation import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("session", help="Tamamen incelenmiş oturumun JSON dosyası")
    parser.add_argument("--tolerance", type=float, default=0.08)
    parser.add_argument("--output")
    args = parser.parse_args()
    if not 0 < args.tolerance < 1:
        parser.error("tolerance must be between 0 and 1 seconds")
    session = Session.from_dict(json.loads(Path(args.session).read_text("utf-8")))
    result = json.dumps(evaluate(session, args.tolerance), ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        Path(args.output).write_text(result, "utf-8")
    print(result)


if __name__ == "__main__":
    main()
