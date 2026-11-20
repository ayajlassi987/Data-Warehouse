
from pathlib import Path
import json
import pandas as pd

from data_quality.quality_rules import run_article_quality_checks
from data_quality.consistency_checks import run_consistency_checks
from data_quality.integrity_checks import run_integrity_checks


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "cleaned_data"
OUTPUT_DIR = BASE_DIR / "output" / "quality_reports"


def run_global_quality_engine():

    print("=" * 65)
    print("PUBMED - GLOBAL DATA QUALITY ENGINE")
    print("=" * 65)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------
    # 1. DATA QUALITY
    # ------------------------------------------------

    print("\n[1/3] Running Data Quality checks...")

    articles_path = DATA_DIR / "articles_clean.csv"

    if not articles_path.exists():
        raise FileNotFoundError(articles_path)

    articles = pd.read_csv(articles_path, dtype=str)

    quality_results = run_article_quality_checks(articles)
    quality_results.insert(0, "category", "DATA_QUALITY")

    print(f"Completed: {len(quality_results)} checks")

    # ------------------------------------------------
    # 2. DATA CONSISTENCY
    # ------------------------------------------------

    print("\n[2/3] Running Data Consistency checks...")

    consistency_results = run_consistency_checks()
    consistency_results.insert(0, "category", "CONSISTENCY")

    print(f"Completed: {len(consistency_results)} checks")

    # ------------------------------------------------
    # 3. DATABASE INTEGRITY
    # ------------------------------------------------

    print("\n[3/3] Running Database Integrity checks...")

    integrity_results = run_integrity_checks()
    integrity_results.insert(0, "category", "INTEGRITY")

    print(f"Completed: {len(integrity_results)} checks")

    # ------------------------------------------------
    # 4. MERGE RESULTS
    # ------------------------------------------------

    print("\nCombining all results...")

    all_results = pd.concat(
        [
            quality_results,
            consistency_results,
            integrity_results
        ],
        ignore_index=True,
        sort=False
    )

    # Consistent column order
    columns = [
        "category",
        "check_name",
        "column_name",
        "table_name",
        "total_records",
        "failed_records",
        "quality_score",
        "status",
        "details"
    ]

    all_results = all_results.reindex(columns=columns)

    # ------------------------------------------------
    # 5. GLOBAL SUMMARY
    # ------------------------------------------------

    summary = {
        "project": "PubMed Data Warehouse",
        "dataset": "articles_clean.csv",
        "database": "pubmed_dw",
        "schema": "dw",
        "dataset_records": len(articles),
        "total_checks": len(all_results),
        "passed_checks": int(
            (all_results["status"] == "PASS").sum()
        ),
        "warning_checks": int(
            (all_results["status"] == "WARNING").sum()
        ),
        "failed_checks": int(
            (all_results["status"] == "FAIL").sum()
        ),
        "error_checks": int(
            (all_results["status"] == "ERROR").sum()
        ),
        "category_summary": {},
        "results": all_results.astype(object)
            .where(pd.notna(all_results), None)
            .to_dict(orient="records")
    }

    for category, group in all_results.groupby("category"):

        summary["category_summary"][category] = {
            "total": len(group),
            "passed": int((group["status"] == "PASS").sum()),
            "warnings": int((group["status"] == "WARNING").sum()),
            "failed": int((group["status"] == "FAIL").sum()),
            "errors": int((group["status"] == "ERROR").sum())
        }

    # ------------------------------------------------
    # 6. EXPORT GLOBAL REPORTS
    # ------------------------------------------------

    csv_path = OUTPUT_DIR / "complete_data_quality_report.csv"
    json_path = OUTPUT_DIR / "complete_data_quality_report.json"

    all_results.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig"
    )

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=4, ensure_ascii=False)

    # ------------------------------------------------
    # 7. DISPLAY SUMMARY
    # ------------------------------------------------

    print("\n" + "=" * 65)
    print("GLOBAL DATA QUALITY SUMMARY")
    print("=" * 65)

    print(f"Total checks : {summary['total_checks']}")
    print(f"PASS         : {summary['passed_checks']}")
    print(f"WARNING      : {summary['warning_checks']}")
    print(f"FAIL         : {summary['failed_checks']}")
    print(f"ERROR        : {summary['error_checks']}")

    print("\nRESULTS BY CATEGORY")

    for category, values in summary["category_summary"].items():
        print(f"\n{category}")
        print(f"  Total   : {values['total']}")
        print(f"  Passed  : {values['passed']}")
        print(f"  Warnings: {values['warnings']}")
        print(f"  Failed  : {values['failed']}")

    print("\nGLOBAL REPORTS GENERATED")
    print(csv_path)
    print(json_path)

    return all_results, summary
