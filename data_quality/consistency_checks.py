
from pathlib import Path
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "cleaned_data"
OUTPUT_DIR = BASE_DIR / "output" / "quality_reports"


RELATION_CONFIG = {
    "authors": {
        "file": "article_authors_clean.csv",
        "count_column": "author_count",
        "value_columns": ["author_order", "author"],
    },
    "keywords": {
        "file": "article_keywords_clean.csv",
        "count_column": "keyword_count",
        "value_columns": ["keyword"],
    },
    "mesh_terms": {
        "file": "article_mesh_terms_clean.csv",
        "count_column": "mesh_count",
        "value_columns": ["mesh_term"],
    },
    "publication_types": {
        "file": "article_publication_types_clean.csv",
        "count_column": None,
        "value_columns": ["publication_type"],
    },
}


def normalize_pmid(series):
    """Normalize PMID values for reliable comparison."""
    return series.astype("string").str.strip()


def check_relation_file(articles, relation_name, config):
    """Check one relationship CSV against the main articles dataset."""

    file_path = DATA_DIR / config["file"]

    if not file_path.exists():
        raise FileNotFoundError(f"Missing file: {file_path}")

    relation = pd.read_csv(file_path, dtype=str)

    required_columns = ["pmid"] + config["value_columns"]
    missing_columns = [
        col for col in required_columns
        if col not in relation.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{config['file']} is missing columns: {missing_columns}"
        )

    articles = articles.copy()
    relation = relation.copy()

    articles["pmid"] = normalize_pmid(articles["pmid"])
    relation["pmid"] = normalize_pmid(relation["pmid"])

    # Remove empty PMID values only for comparison.
    valid_relation = relation[
        relation["pmid"].notna()
        & relation["pmid"].ne("")
    ].copy()

    valid_articles = articles[
        articles["pmid"].notna()
        & articles["pmid"].ne("")
    ].copy()

    article_pmids = set(valid_articles["pmid"])
    relation_pmids = set(valid_relation["pmid"])

    # 1. Missing and unknown PMID checks
    missing_pmid_count = int(
        relation["pmid"].isna().sum()
        + relation["pmid"].eq("").sum()
    )

    orphan_pmids = relation_pmids - article_pmids

    # 2. Duplicate relationship checks
    duplicate_columns = ["pmid"] + config["value_columns"]

    duplicate_rows = valid_relation[
        valid_relation.duplicated(
            subset=duplicate_columns,
            keep=False
        )
    ].copy()

    # 3. Compare relationship counts with articles_clean.csv
    count_mismatches = pd.DataFrame()

    count_column = config["count_column"]

    if count_column:
        if count_column not in valid_articles.columns:
            raise ValueError(
                f"Column '{count_column}' not found in articles_clean.csv"
            )

        expected = valid_articles[["pmid", count_column]].copy()

        expected[count_column] = pd.to_numeric(
            expected[count_column],
            errors="coerce"
        )

        actual = (
            valid_relation.groupby("pmid")
            .size()
            .reset_index(name="actual_count")
        )

        comparison = expected.merge(
            actual,
            on="pmid",
            how="left"
        )

        comparison["actual_count"] = (
            comparison["actual_count"].fillna(0).astype(int)
        )

        comparison["expected_count"] = comparison[count_column]

        count_mismatches = comparison[
            comparison["expected_count"].notna()
            & (
                comparison["expected_count"]
                != comparison["actual_count"]
            )
        ][["pmid", "expected_count", "actual_count"]].copy()

    # 4. Summary results
    results = [
        {
            "check_name": f"{relation_name}_missing_pmid",
            "total_records": len(relation),
            "failed_records": missing_pmid_count,
            "status": "PASS" if missing_pmid_count == 0 else "FAIL",
            "details": f"{missing_pmid_count} rows without PMID",
        },
        {
            "check_name": f"{relation_name}_orphan_pmid",
            "total_records": len(valid_relation),
            "failed_records": len(orphan_pmids),
            "status": "PASS" if not orphan_pmids else "FAIL",
            "details": f"{len(orphan_pmids)} unknown PMIDs",
        },
        {
            "check_name": f"{relation_name}_duplicate_rows",
            "total_records": len(valid_relation),
            "failed_records": len(duplicate_rows),
            "status": "PASS" if duplicate_rows.empty else "WARNING",
            "details": f"{len(duplicate_rows)} rows involved in duplicate associations",
        },
    ]

    if count_column:
        results.append({
            "check_name": f"{relation_name}_count_consistency",
            "total_records": len(valid_articles),
            "failed_records": len(count_mismatches),
            "status": "PASS" if count_mismatches.empty else "FAIL",
            "details": (
                f"{len(count_mismatches)} articles with inconsistent counts"
            ),
        })

    return results, {
        "relation_name": relation_name,
        "duplicate_rows": duplicate_rows,
        "count_mismatches": count_mismatches,
        "orphan_pmids": sorted(orphan_pmids),
    }


def run_consistency_checks():
    """Run consistency checks on all relationship CSV files."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    articles_path = DATA_DIR / "articles_clean.csv"

    if not articles_path.exists():
        raise FileNotFoundError(articles_path)

    articles = pd.read_csv(articles_path, dtype=str)

    if "pmid" not in articles.columns:
        raise ValueError("Column 'pmid' is missing from articles_clean.csv")

    all_results = []
    all_details = []

    for relation_name, config in RELATION_CONFIG.items():
        results, details = check_relation_file(
            articles,
            relation_name,
            config
        )

        all_results.extend(results)
        all_details.append(details)

    results_df = pd.DataFrame(all_results)

    # Export summary
    results_df.to_csv(
        OUTPUT_DIR / "consistency_quality_report.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Export detailed discrepancy files
    for details in all_details:
        name = details["relation_name"]

        details["duplicate_rows"].to_csv(
            OUTPUT_DIR / f"{name}_duplicate_rows.csv",
            index=False,
            encoding="utf-8-sig"
        )

        details["count_mismatches"].to_csv(
            OUTPUT_DIR / f"{name}_count_mismatches.csv",
            index=False,
            encoding="utf-8-sig"
        )

        pd.DataFrame(
            {"orphan_pmid": details["orphan_pmids"]}
        ).to_csv(
            OUTPUT_DIR / f"{name}_orphan_pmids.csv",
            index=False,
            encoding="utf-8-sig"
        )

    return results_df
