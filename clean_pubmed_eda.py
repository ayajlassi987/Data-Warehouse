"""
Conservative cleaning for the PubMed EDA outputs.

Input:
  eda_output/articles_eda.csv
  eda_output/article_authors.csv
  eda_output/article_keywords.csv
  eda_output/article_mesh_terms.csv
  eda_output/article_publication_types.csv
  eda_output/xml_errors.csv (optional)

Output:
  cleaned_data/  (cleaned CSVs + audit reports)

Run:
  python clean_pubmed_eda.py --input eda_output --output cleaned_data

Principles:
- Never overwrite the EDA/raw files.
- Do not invent missing abstracts, DOIs, dates, keywords, or MeSH terms.
- Remove duplicate PMIDs only after exporting the duplicate rows for review.
- Normalize whitespace and identifier formats conservatively.
- Keep missing-value flags and a cleaning log for traceability.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"WARNING: optional input not found: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"pmid": "string"}, keep_default_na=True)


def clean_text(value):
    """Trim and collapse repeated whitespace; keep meaningful punctuation/case."""
    if pd.isna(value):
        return pd.NA
    value = str(value).replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value if value else pd.NA


def normalize_pmid(series: pd.Series) -> pd.Series:
    """PMIDs are identifiers: store as strings, not integers."""
    out = series.astype("string").str.strip()
    out = out.str.replace(r"\.0$", "", regex=True)  # handles CSVs that inferred numeric IDs
    out = out.mask(out.eq(""))
    return out


def normalize_doi(value):
    """Standardize DOI representation without claiming that the DOI is valid."""
    value = clean_text(value)
    if pd.isna(value):
        return pd.NA
    doi = str(value).strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    doi = doi.strip().lower()
    return doi if doi else pd.NA


def normalize_pipe_list(value, case_insensitive_dedup=False):
    """
    Clean a pipe-separated field from the EDA export.
    Relationship tables remain the preferred source for dimensional modeling.
    """
    value = clean_text(value)
    if pd.isna(value):
        return pd.NA
    parts = [clean_text(x) for x in str(value).split("|")]
    parts = [str(x) for x in parts if not pd.isna(x)]
    seen = set()
    result = []
    for part in parts:
        key = part.casefold() if case_insensitive_dedup else part
        if key not in seen:
            seen.add(key)
            result.append(part)
    return " | ".join(result) if result else pd.NA


def canonical_publication_type(value):
    value = clean_text(value)
    if pd.isna(value):
        return pd.NA
    # Known casing variant seen in the EDA output.
    if str(value).casefold() == "journal article":
        return "Journal Article"
    return str(value)


def choose_best_duplicate_rows(df: pd.DataFrame, key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Export every row involved in a duplicate key, then keep the most complete
    row per key. Ties retain the first row in stable input order.
    """
    valid_key = df[key].notna() & df[key].astype("string").str.strip().ne("")
    duplicate_mask = valid_key & df[key].duplicated(keep=False)
    duplicates = df.loc[duplicate_mask].copy()
    if df.empty or not duplicate_mask.any():
        return df.copy(), duplicates

    work = df.copy()
    # Score completeness on substantive fields, not source_file or derived lengths.
    score_cols = [
        c for c in [
            "title", "abstract", "journal", "year", "doi", "authors",
            "keywords", "mesh_terms", "publication_types", "language"
        ] if c in work.columns
    ]
    work["_completeness_score"] = work[score_cols].notna().sum(axis=1)
    work["_original_order"] = range(len(work))
    work = work.sort_values(
        [key, "_completeness_score", "_original_order"],
        ascending=[True, False, True],
        kind="stable"
    )
    deduped = work.drop_duplicates(subset=[key], keep="first")
    deduped = deduped.drop(columns=["_completeness_score", "_original_order"])
    return deduped.reset_index(drop=True), duplicates.reset_index(drop=True)


def clean_articles(input_dir: Path, output_dir: Path):
    source = input_dir / "articles_eda.csv"
    if not source.exists():
        raise FileNotFoundError(
            f"Could not find {source}. Use the folder containing articles_eda.csv."
        )

    df = pd.read_csv(source, dtype={"pmid": "string"})
    initial_rows = len(df)

    # Normalize common text fields.
    text_cols = [
        "title", "abstract", "journal", "publication_date_text", "language",
        "authors", "keywords", "mesh_terms", "publication_types", "source_file"
    ]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].map(clean_text).astype("string")

    if "pmid" in df.columns:
        df["pmid"] = normalize_pmid(df["pmid"])
    if "doi" in df.columns:
        df["doi"] = df["doi"].map(normalize_doi).astype("string")

    # Normalize list-like columns but preserve their semantics and order.
    for col in ["authors", "keywords", "mesh_terms", "publication_types"]:
        if col in df.columns:
            df[col] = df[col].map(
                lambda x: normalize_pipe_list(x, case_insensitive_dedup=(col != "authors"))
            ).astype("string")

    # Normalize known publication-type casing differences in the flat export.
    if "publication_types" in df.columns:
        df["publication_types"] = df["publication_types"].map(
            lambda x: " | ".join(
                canonical_publication_type(part)
                for part in str(x).split(" | ")
            ) if not pd.isna(x) else pd.NA
        ).astype("string")

    # Convert numeric columns carefully. Do not replace missing values with zero.
    for col in [
        "year", "author_count", "keyword_count", "mesh_count",
        "title_chars", "abstract_chars", "abstract_words"
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "year" in df.columns:
        # Flag, do not silently delete, years outside a conservative plausible range.
        df["year_out_of_range_flag"] = df["year"].notna() & (
            (df["year"] < 1500) | (df["year"] > pd.Timestamp.now().year + 1)
        )
        df["year"] = df["year"].mask(df["year_out_of_range_flag"]).astype("Int64")

    # Capture duplicates before deduplication. A duplicate PMID is the strongest
    # evidence of the same PubMed record; DOI duplicates alone are not auto-dropped.
    deduped, duplicate_pmids = choose_best_duplicate_rows(df, "pmid")
    duplicate_pmids.to_csv(output_dir / "duplicate_pmids_before_cleaning.csv", index=False)

    # Record repeated DOI for manual review; a DOI can occasionally be shared by
    # related records or represented inconsistently, so do not drop based on DOI alone.
    doi_duplicates = pd.DataFrame()
    if "doi" in deduped.columns:
        mask = deduped["doi"].notna() & deduped["doi"].duplicated(keep=False)
        doi_duplicates = deduped.loc[mask].sort_values("doi")
    doi_duplicates.to_csv(output_dir / "duplicate_dois_for_review.csv", index=False)

    # Missingness audit before any optional fields are filled (none are filled here).
    missing_rows = []
    for col in deduped.columns:
        if col.endswith("_flag"):
            continue
        missing_mask = deduped[col].isna()
        if deduped[col].dtype == "string" or deduped[col].dtype == object:
            missing_mask = missing_mask | deduped[col].astype("string").str.strip().eq("")
        missing_rows.append({
            "column": col,
            "missing_count": int(missing_mask.sum()),
            "missing_percent": round(float(missing_mask.mean() * 100), 2),
            "total_rows": len(deduped),
        })
    pd.DataFrame(missing_rows).sort_values(
        "missing_percent", ascending=False
    ).to_csv(output_dir / "missing_values_after_cleaning.csv", index=False)

    # Useful flags for downstream decisions; keep rows for review.
    for col, flag in [
        ("abstract", "missing_abstract_flag"),
        ("doi", "missing_doi_flag"),
        ("journal", "missing_journal_flag"),
        ("year", "missing_year_flag"),
        ("keywords", "missing_keywords_flag"),
        ("mesh_terms", "missing_mesh_terms_flag"),
        ("authors", "missing_authors_flag"),
    ]:
        if col in deduped.columns:
            deduped[flag] = deduped[col].isna()

    # Recompute derived lengths after whitespace normalization.
    if "title" in deduped.columns:
        deduped["title_chars_clean"] = deduped["title"].str.len().astype("Int64")
    if "abstract" in deduped.columns:
        deduped["abstract_chars_clean"] = deduped["abstract"].str.len().astype("Int64")
        deduped["abstract_words_clean"] = deduped["abstract"].map(
            lambda x: len(str(x).split()) if not pd.isna(x) else pd.NA
        ).astype("Int64")

    deduped.to_csv(output_dir / "articles_clean.csv", index=False)

    audit = pd.DataFrame([
        {"metric": "article_rows_before_cleaning", "value": initial_rows},
        {"metric": "article_rows_after_deduplication", "value": len(deduped)},
        {"metric": "rows_removed_as_duplicate_pmid", "value": initial_rows - len(deduped)},
        {"metric": "unique_nonmissing_pmids_after_cleaning",
         "value": deduped["pmid"].nunique(dropna=True) if "pmid" in deduped.columns else 0},
        {"metric": "duplicate_pmid_rows_flagged_before_cleaning", "value": len(duplicate_pmids)},
        {"metric": "rows_with_missing_abstract",
         "value": int(deduped["abstract"].isna().sum()) if "abstract" in deduped.columns else 0},
        {"metric": "rows_with_missing_doi",
         "value": int(deduped["doi"].isna().sum()) if "doi" in deduped.columns else 0},
    ])
    audit.to_csv(output_dir / "cleaning_audit.csv", index=False)
    return deduped


def clean_relationship_table(input_dir: Path, output_dir: Path, filename: str,
                             id_col: str, value_col: str, extra_key_cols=None):
    source = input_dir / filename
    if not source.exists():
        return

    rel = pd.read_csv(source, dtype={"pmid": "string"})
    if "pmid" in rel.columns:
        rel["pmid"] = normalize_pmid(rel["pmid"])
    if value_col in rel.columns:
        rel[value_col] = rel[value_col].map(clean_text).astype("string")

    # Normalize known publication type casing only.
    if value_col == "publication_type":
        rel[value_col] = rel[value_col].map(canonical_publication_type).astype("string")

    # Drop only exact duplicate relationships, not records merely sharing a value.
    subset = [c for c in [id_col, value_col] if c in rel.columns]
    # Author order is part of the relationship grain: keep the same named author
    # if it occurs at a different position, and only remove duplicate positions.
    for col in (extra_key_cols or []):
        if col in rel.columns and col not in subset:
            subset.append(col)
    before = len(rel)
    if subset:
        rel = rel.dropna(subset=subset).drop_duplicates(subset=subset)
    rel.to_csv(output_dir / filename.replace(".csv", "_clean.csv"), index=False)

    pd.DataFrame([{
        "file": filename,
        "rows_before": before,
        "rows_after": len(rel),
        "exact_relationship_rows_removed": before - len(rel),
    }]).to_csv(output_dir / (filename.replace(".csv", "_cleaning_audit.csv")), index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="eda_output", help="Folder containing EDA CSV outputs")
    parser.add_argument("--output", default="cleaned_data", help="Folder for cleaned outputs")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    articles = clean_articles(input_dir, output_dir)

    clean_relationship_table(
        input_dir, output_dir, "article_authors.csv", "pmid", "author",
        extra_key_cols=["author_order"]
    )
    clean_relationship_table(
        input_dir, output_dir, "article_keywords.csv", "pmid", "keyword"
    )
    clean_relationship_table(
        input_dir, output_dir, "article_mesh_terms.csv", "pmid", "mesh_term"
    )
    clean_relationship_table(
        input_dir, output_dir, "article_publication_types.csv", "pmid", "publication_type"
    )

    # Carry XML parsing errors into the cleaning deliverables; do not pretend these
    # records were recovered by CSV cleaning.
    xml_errors = read_csv_if_exists(input_dir / "xml_errors.csv")
    if not xml_errors.empty:
        xml_errors.to_csv(output_dir / "xml_errors_for_recovery.csv", index=False)

    print("\nCleaning finished.")
    print(f"Input article rows: {len(pd.read_csv(input_dir / 'articles_eda.csv'))}")
    print(f"Clean article rows: {len(articles)}")
    print(f"Outputs saved to: {output_dir.resolve()}")
    print("Read cleaning_audit.csv and missing_values_after_cleaning.csv first.")


if __name__ == "__main__":
    main()
