
import pandas as pd


def is_missing(series):
    """Detect missing values, including empty strings."""
    return (
        series.isna()
        | series.astype("string").str.strip().eq("")
    )


def check_completeness(df, column):
    """Calculate the completeness rate of a column."""
    if column not in df.columns:
        return {
            "check_name": f"{column}_completeness",
            "column_name": column,
            "total_records": len(df),
            "failed_records": len(df),
            "quality_score": 0.0,
            "status": "ERROR",
            "details": "Column not found"
        }

    missing_count = int(is_missing(df[column]).sum())
    total = len(df)
    score = ((total - missing_count) / total * 100) if total else 100.0

    required_columns = ["pmid", "title"]
    status = (
        "FAIL" if missing_count > 0 and column in required_columns
        else "WARNING" if missing_count > 0
        else "PASS"
    )

    return {
        "check_name": f"{column}_completeness",
        "column_name": column,
        "total_records": total,
        "failed_records": missing_count,
        "quality_score": round(score, 2),
        "status": status,
        "details": f"{missing_count} missing values"
    }


def check_uniqueness(df, column):
    """Detect duplicate non-empty values."""
    if column not in df.columns:
        return {
            "check_name": f"{column}_uniqueness",
            "column_name": column,
            "total_records": len(df),
            "failed_records": len(df),
            "quality_score": 0.0,
            "status": "ERROR",
            "details": "Column not found"
        }

    valid = df.loc[~is_missing(df[column]), column]
    duplicates = int(valid.duplicated(keep="first").sum())

    total = len(valid)
    score = ((total - duplicates) / total * 100) if total else 100.0

    return {
        "check_name": f"{column}_uniqueness",
        "column_name": column,
        "total_records": total,
        "failed_records": duplicates,
        "quality_score": round(score, 2),
        "status": "FAIL" if duplicates else "PASS",
        "details": f"{duplicates} duplicate values"
    }


def check_year_validity(df, min_year=2012, max_year=2016):
    """Check whether non-empty publication years are valid."""
    column = "year"

    if column not in df.columns:
        return {
            "check_name": "year_validity",
            "column_name": column,
            "total_records": len(df),
            "failed_records": len(df),
            "quality_score": 0.0,
            "status": "ERROR",
            "details": "Column not found"
        }

    values = df.loc[~is_missing(df[column]), column]
    numeric_years = pd.to_numeric(values, errors="coerce")

    invalid = (
        numeric_years.isna()
        | ~numeric_years.between(min_year, max_year)
        | (numeric_years % 1 != 0)
    )

    failed = int(invalid.sum())
    total = len(values)
    score = ((total - failed) / total * 100) if total else 100.0

    return {
        "check_name": "year_validity",
        "column_name": column,
        "total_records": total,
        "failed_records": failed,
        "quality_score": round(score, 2),
        "status": "WARNING" if failed else "PASS",
        "details": f"{failed} invalid non-empty years"
    }


def run_article_quality_checks(df):
    """Execute all initial quality checks on articles."""

    results = []

    # Completeness checks
    for column in [
        "pmid",
        "title",
        "doi",
        "abstract",
        "journal",
        "year"
    ]:
        results.append(check_completeness(df, column))

    # Uniqueness checks
    results.append(check_uniqueness(df, "pmid"))
    results.append(check_uniqueness(df, "doi"))

    # Validity checks
    results.append(check_year_validity(df))

    return pd.DataFrame(results)
