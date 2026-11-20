
from data_quality.consistency_checks import run_consistency_checks


def main():
    print("=" * 60)
    print("PUBMED - DATA CONSISTENCY CHECKS")
    print("=" * 60)

    results = run_consistency_checks()

    print("\nCONSISTENCY RESULTS")
    print("-" * 60)
    print(results.to_string(index=False))

    print("\nSUMMARY")
    print("-" * 60)
    print(f"Passed  : {(results['status'] == 'PASS').sum()}")
    print(f"Warnings: {(results['status'] == 'WARNING').sum()}")
    print(f"Failed  : {(results['status'] == 'FAIL').sum()}")

    print("\nReports generated in:")
    print("output/quality_reports/")


if __name__ == "__main__":
    main()
