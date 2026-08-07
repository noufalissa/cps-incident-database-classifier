"""Run a batch outside Streamlit and save CSV outputs to outputs/."""

from pathlib import Path
import argparse
import pandas as pd

from batch_processor import batch_classify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/incidents.csv")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--max-urls", type=int, default=1)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.input).fillna("")
    result = batch_classify(
        df,
        fetch_urls=not args.no_fetch,
        max_urls_per_incident=args.max_urls,
        max_workers=args.workers,
        max_properties=3,
        row_start=args.start,
        row_end=args.end,
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(result.visualization_rows).to_csv(
        out / "visualization_properties.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(result.incident_qc_rows).to_csv(
        out / "incident_classification_qc.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(result.url_fetch_rows).to_csv(
        out / "url_fetch_status.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(result.manual_review_rows).to_csv(
        out / "manual_review_queue.csv", index=False, encoding="utf-8-sig"
    )

    print(f"Processed rows: {len(result.incident_qc_rows)}")
    print(f"Visualization rows: {len(result.visualization_rows)}")
    print(f"Saved outputs to: {out.resolve()}")


if __name__ == "__main__":
    main()
