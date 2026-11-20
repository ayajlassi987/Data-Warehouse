
from pathlib import Path
import json
import pandas as pd

from data_quality.quality_rules import run_article_quality_checks


# Project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "cleaned_data"
OUTPUT_DIR = BASE_DIR / "output" / "quality_reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = DATA_DIR / "articles_clean.csv"


def main():
    print("=" * 55)
    print("PUBMED - DATA QUALITY ENGINE")
    print("=" * 55)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    print("\nLoading articles dataset...")

    df = pd.read_csv(
        INPUT_FILE,
        dtype=str,
        keep_default_na=True
    )

    print(f"Records loaded: {len(df)}")
    print(f"Columns detected: {len(df.columns)}")

    print("\nRunning quality checks...")

    results = run_article_quality_checks(df)

    # Export CSV report
    csv_path = OUTPUT_DIR / "articles_quality_report.csv"
    results.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Export JSON report
    json_path = OUTPUT_DIR / "articles_quality_report.json"

    report = {
        "dataset": "articles_clean.csv",
        "total_records": len(df),
        "total_checks": len(results),
        "passed_checks": int((results["status"] == "PASS").sum()),
        "warning_checks": int((results["status"] == "WARNING").sum()),
        "failed_checks": int((results["status"] == "FAIL").sum()),
        "error_checks": int((results["status"] == "ERROR").sum()),
        "results": results.to_dict(orient="records")
    }

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    print("\nQUALITY RESULTS")
    print("-" * 55)
    print(results.to_string(index=False))

    print("\nREPORT SUMMARY")
    print("-" * 55)
    print(f"Passed checks : {report['passed_checks']}")
    print(f"Warnings      : {report['warning_checks']}")
    print(f"Failed checks : {report['failed_checks']}")
    print(f"Errors        : {report['error_checks']}")

    print("\nReports generated successfully:")
    print(csv_path)
    print(json_path)


if __name__ == "__main__":
    main()
