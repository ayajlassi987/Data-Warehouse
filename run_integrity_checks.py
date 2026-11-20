
from data_quality.integrity_checks import run_integrity_checks


def main():
    print("=" * 60)
    print("PUBMED - DATABASE INTEGRITY ENGINE")
    print("=" * 60)

    print("\nConnecting to PostgreSQL through Docker...")
    print("Running integrity checks...\n")

    results = run_integrity_checks()

    print("INTEGRITY RESULTS")
    print("-" * 60)
    print(results.to_string(index=False))

    print("\nREPORT SUMMARY")
    print("-" * 60)
    print(f"Total checks : {len(results)}")
    print(f"Passed       : {(results['status'] == 'PASS').sum()}")
    print(f"Warnings     : {(results['status'] == 'WARNING').sum()}")
    print(f"Failed       : {(results['status'] == 'FAIL').sum()}")

    print("\nReports generated:")
    print("output/quality_reports/database_integrity_report.csv")
    print("output/quality_reports/database_integrity_report.json")


if __name__ == "__main__":
    main()
