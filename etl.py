import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

CSV_FILES = {
    "articles": os.getenv(
        "ARTICLES_CSV",
        "cleaned_data/articles_clean.csv"
    ),
    "authors": os.getenv(
        "AUTHORS_CSV",
        "cleaned_data/article_authors_clean.csv"
    ),
    "keywords": os.getenv(
        "KEYWORDS_CSV",
        "cleaned_data/article_keywords_clean.csv"
    ),
    "mesh_terms": os.getenv(
        "MESH_TERMS_CSV",
        "cleaned_data/article_mesh_terms_clean.csv"
    ),
    "publication_types": os.getenv(
        "PUBLICATION_TYPES_CSV",
        "cleaned_data/article_publication_types_clean.csv"
    ),
}

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "dbname": os.getenv("DB_NAME", "pubmed_dw"),
    "user": os.getenv("DB_USER", "pubmed_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


# ============================================================
# 2. LOAD AND VALIDATE CSV FILES
# ============================================================

def load_csv_files():
    """Load the five cleaned datasets and validate their columns."""

    data = {}

    required_columns = {
        "articles": {
            "pmid",
            "title",
            "abstract",
            "journal",
            "year",
            "publication_date_text",
            "language",
            "doi",
        },
        "authors": {
            "pmid",
            "author_order",
            "author",
        },
        "keywords": {
            "pmid",
            "keyword",
        },
        "mesh_terms": {
            "pmid",
            "mesh_term",
        },
        "publication_types": {
            "pmid",
            "publication_type",
        },
    }

    for dataset_name, relative_path in CSV_FILES.items():
        file_path = BASE_DIR / relative_path

        if not file_path.exists():
            raise FileNotFoundError(
                f"Missing CSV file: {file_path}"
            )

        df = pd.read_csv(
            file_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

        df.columns = df.columns.str.strip()

        missing_columns = (
            required_columns[dataset_name] - set(df.columns)
        )

        if missing_columns:
            raise ValueError(
                f"{dataset_name}: missing columns "
                f"{sorted(missing_columns)}"
            )

        # Normalize identifiers and remove surrounding whitespace.
        df["pmid"] = df["pmid"].str.strip()

        data[dataset_name] = df

        print(
            f"Loaded {dataset_name}: "
            f"{len(df):,} rows from {file_path.name}"
        )

    return data


# ============================================================
# 3. DATA CLEANING HELPERS
# ============================================================

def clean_text(value):
    """Convert empty strings and textual nulls to SQL NULL."""

    if value is None:
        return None

    value = str(value).strip()

    if value.lower() in {"", "nan", "none", "null", "n/a"}:
        return None

    return value


def clean_integer(value):
    """Convert a value to an integer, or return None."""

    value = clean_text(value)

    if value is None:
        return None

    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def unique_text_values(values):
    """Return distinct, non-empty values while preserving order."""

    result = []
    seen = set()

    for value in values:
        value = clean_text(value)

        if value is not None and value not in seen:
            result.append(value)
            seen.add(value)

    return result


# ============================================================
# 4. INSERT DIMENSION VALUES
# ============================================================

def insert_dimension_values(
    cursor,
    table_name,
    column_name,
    values,
):
    """Insert unique dimension values and return their IDs."""

    values = unique_text_values(values)

    if not values:
        return {}

    query = f"""
        INSERT INTO dw.{table_name} ({column_name})
        VALUES %s
        ON CONFLICT ({column_name}) DO NOTHING;
    """

    execute_values(
        cursor,
        query,
        [(value,) for value in values],
    )

    cursor.execute(
        f"""
        SELECT {column_name}, 
               {table_name.replace("dim_", "")}_id
        FROM dw.{table_name};
        """
    )

    return dict(cursor.fetchall())


# ============================================================
# 5. LOAD ARTICLE DIMENSIONS AND FACT TABLE
# ============================================================

def load_articles(cursor, articles):
    """Load journals, years, and the central article fact table."""

    articles = articles.copy()

    # Empty PMIDs cannot serve as primary keys.
    missing_pmid = articles["pmid"].eq("")

    print(
        f"Articles skipped due to missing PMID: "
        f"{missing_pmid.sum():,}"
    )

    articles = articles.loc[~missing_pmid].copy()

    # Keep the first record for each PMID.
    duplicate_mask = articles["pmid"].duplicated(keep="first")

    duplicate_count = int(duplicate_mask.sum())

    if duplicate_count:
        duplicate_path = BASE_DIR / "output"
        duplicate_path.mkdir(exist_ok=True)

        articles.loc[duplicate_mask].to_csv(
            duplicate_path / "duplicate_pmids_etl.csv",
            index=False,
            encoding="utf-8-sig",
        )

        print(
            f"Duplicate article records excluded: "
            f"{duplicate_count:,}"
        )

    articles = articles.loc[~duplicate_mask].copy()

    # Insert journal dimension.
    journal_map = insert_dimension_values(
        cursor,
        "dim_journal",
        "journal_name",
        articles["journal"],
    )

    # Insert publication-year dimension.
    valid_years = []

    for value in articles["year"]:
        year = clean_integer(value)

        # Avoid creating meaningless year records.
        if year is not None and 1000 <= year <= 2100:
            valid_years.append(year)

    valid_years = sorted(set(valid_years))

    execute_values(
        cursor,
        """
        INSERT INTO dw.dim_year (year_id)
        VALUES %s
        ON CONFLICT (year_id) DO NOTHING;
        """,
        [(year,) for year in valid_years],
    )

    year_map = {
        year: year
        for year in valid_years
    }

    fact_rows = []

    for _, row in articles.iterrows():
        pmid = clean_text(row["pmid"])

        journal = clean_text(row["journal"])
        year = clean_integer(row["year"])

        journal_id = (
            journal_map.get(journal)
            if journal is not None
            else None
        )

        year_id = (
            year_map.get(year)
            if year is not None
            else None
        )

        fact_rows.append(
            (
                pmid,
                clean_text(row["title"]),
                clean_text(row["abstract"]),
                clean_text(row["doi"]),
                clean_text(row["language"]),
                clean_text(row["publication_date_text"]),
                journal_id,
                year_id,
                clean_integer(row.get("author_count")),
                clean_integer(row.get("keyword_count")),
                clean_integer(row.get("mesh_count")),
                clean_integer(row.get("abstract_words_clean"))
                or clean_integer(row.get("abstract_words")),
            )
        )

    execute_values(
        cursor,
        """
        INSERT INTO dw.fact_article (
            pmid,
            title,
            abstract,
            doi,
            language,
            publication_date_text,
            journal_id,
            year_id,
            author_count,
            keyword_count,
            mesh_count,
            abstract_words
        )
        VALUES %s;
        """,
        fact_rows,
        page_size=1000,
    )

    print(f"Articles loaded: {len(fact_rows):,}")

    return {row[0] for row in fact_rows}


# ============================================================
# 6. LOAD AUTHORS AND ARTICLE-AUTHOR RELATIONSHIPS
# ============================================================

def load_authors(cursor, authors, valid_pmids):
    authors = authors.copy()

    authors["author"] = authors["author"].map(clean_text)
    authors = authors[
        authors["pmid"].isin(valid_pmids)
        & authors["author"].notna()
    ].copy()

    author_map = insert_dimension_values(
        cursor,
        "dim_author",
        "author_name",
        authors["author"],
    )

    relationships = []

    for _, row in authors.iterrows():
        author_id = author_map[row["author"]]
        author_order = clean_integer(row["author_order"])

        relationships.append(
            (
                row["pmid"],
                author_id,
                author_order,
            )
        )

    # If an article has the same author more than once,
    # keep the first relationship.
    unique_relationships = {}
    for pmid, author_id, order in relationships:
        unique_relationships.setdefault(
            (pmid, author_id),
            (pmid, author_id, order),
        )

    execute_values(
        cursor,
        """
        INSERT INTO dw.bridge_article_author (
            pmid, author_id, author_order
        )
        VALUES %s
        ON CONFLICT (pmid, author_id) DO NOTHING;
        """,
        list(unique_relationships.values()),
        page_size=1000,
    )

    print(
        f"Article-author relationships loaded: "
        f"{len(unique_relationships):,}"
    )


# ============================================================
# 7. LOAD KEYWORDS AND RELATIONSHIPS
# ============================================================

def load_keywords(cursor, keywords, valid_pmids):
    keywords = keywords.copy()

    keywords["keyword"] = keywords["keyword"].map(clean_text)

    keywords = keywords[
        keywords["pmid"].isin(valid_pmids)
        & keywords["keyword"].notna()
    ].copy()

    keyword_map = insert_dimension_values(
        cursor,
        "dim_keyword",
        "keyword",
        keywords["keyword"],
    )

    relationships = {
        (row.pmid, keyword_map[row.keyword])
        for row in keywords.itertuples(index=False)
    }

    execute_values(
        cursor,
        """
        INSERT INTO dw.bridge_article_keyword (
            pmid, keyword_id
        )
        VALUES %s
        ON CONFLICT DO NOTHING;
        """,
        list(relationships),
        page_size=1000,
    )

    print(
        f"Article-keyword relationships loaded: "
        f"{len(relationships):,}"
    )


# ============================================================
# 8. LOAD MESH TERMS AND RELATIONSHIPS
# ============================================================

def load_mesh_terms(cursor, mesh_terms, valid_pmids):
    mesh_terms = mesh_terms.copy()

    mesh_terms["mesh_term"] = (
        mesh_terms["mesh_term"].map(clean_text)
    )

    mesh_terms = mesh_terms[
        mesh_terms["pmid"].isin(valid_pmids)
        & mesh_terms["mesh_term"].notna()
    ].copy()

    mesh_map = insert_dimension_values(
        cursor,
        "dim_mesh_term",
        "mesh_term",
        mesh_terms["mesh_term"],
    )

    relationships = {
        (row.pmid, mesh_map[row.mesh_term])
        for row in mesh_terms.itertuples(index=False)
    }

    execute_values(
        cursor,
        """
        INSERT INTO dw.bridge_article_mesh (
            pmid, mesh_term_id
        )
        VALUES %s
        ON CONFLICT DO NOTHING;
        """,
        list(relationships),
        page_size=1000,
    )

    print(
        f"Article-MeSH relationships loaded: "
        f"{len(relationships):,}"
    )


# ============================================================
# 9. LOAD PUBLICATION TYPES AND RELATIONSHIPS
# ============================================================

def load_publication_types(
    cursor,
    publication_types,
    valid_pmids,
):
    publication_types = publication_types.copy()

    publication_types["publication_type"] = (
        publication_types["publication_type"].map(clean_text)
    )

    publication_types = publication_types[
        publication_types["pmid"].isin(valid_pmids)
        & publication_types["publication_type"].notna()
    ].copy()

    type_map = insert_dimension_values(
        cursor,
        "dim_publication_type",
        "publication_type",
        publication_types["publication_type"],
    )

    relationships = {
        (row.pmid, type_map[row.publication_type])
        for row in publication_types.itertuples(index=False)
    }

    execute_values(
        cursor,
        """
        INSERT INTO dw.bridge_article_publication_type (
            pmid, publication_type_id
        )
        VALUES %s
        ON CONFLICT DO NOTHING;
        """,
        list(relationships),
        page_size=1000,
    )

    print(
        f"Article-publication-type relationships loaded: "
        f"{len(relationships):,}"
    )


# ============================================================
# 10. MAIN ETL PIPELINE
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("PUBMED DATA WAREHOUSE - ETL PIPELINE")
    print("=" * 60)

    if not DB_CONFIG["password"]:
        raise ValueError(
            "POSTGRES_PASSWORD is missing from your .env file."
        )

    # Load and validate input files before connecting to PostgreSQL.
    data = load_csv_files()

    # Check whether relationship files contain PMIDs absent
    # from the article dataset.
    article_pmids = set(
        data["articles"]["pmid"]
    ) - {""}

    for dataset_name in (
        "authors",
        "keywords",
        "mesh_terms",
        "publication_types",
    ):
        relationship_pmids = set(
            data[dataset_name]["pmid"]
        ) - {""}

        orphan_pmids = relationship_pmids - article_pmids

        print(
            f"{dataset_name}: "
            f"{len(orphan_pmids):,} distinct PMIDs "
            "not found in the article CSV"
        )

    schema_path = BASE_DIR / "schema.sql"

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}"
        )

    print("\nConnecting to PostgreSQL...")

    connection = psycopg2.connect(**DB_CONFIG)

    try:
        with connection:
            with connection.cursor() as cursor:

                # Create tables if they do not already exist.
                cursor.execute(
                    schema_path.read_text(encoding="utf-8")
                )

                # Full refresh: clear previous DW contents in
                # dependency-safe order. This is destructive.
                cursor.execute(
                    """
                    TRUNCATE TABLE
                        dw.bridge_article_author,
                        dw.bridge_article_keyword,
                        dw.bridge_article_mesh,
                        dw.bridge_article_publication_type,
                        dw.fact_article,
                        dw.dim_author,
                        dw.dim_keyword,
                        dw.dim_mesh_term,
                        dw.dim_publication_type,
                        dw.dim_journal,
                        dw.dim_year
                    RESTART IDENTITY;
                    """
                )

                valid_pmids = load_articles(
                    cursor,
                    data["articles"],
                )

                load_authors(
                    cursor,
                    data["authors"],
                    valid_pmids,
                )

                load_keywords(
                    cursor,
                    data["keywords"],
                    valid_pmids,
                )

                load_mesh_terms(
                    cursor,
                    data["mesh_terms"],
                    valid_pmids,
                )

                load_publication_types(
                    cursor,
                    data["publication_types"],
                    valid_pmids,
                )

                # Report final table sizes.
                tables = [
                    "fact_article",
                    "dim_journal",
                    "dim_year",
                    "dim_author",
                    "dim_keyword",
                    "dim_mesh_term",
                    "dim_publication_type",
                    "bridge_article_author",
                    "bridge_article_keyword",
                    "bridge_article_mesh",
                    "bridge_article_publication_type",
                ]

                print("\nFINAL TABLE COUNTS")
                print("-" * 40)

                for table in tables:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM dw.{table};"
                    )

                    count = cursor.fetchone()[0]

                    print(f"{table:<40} {count:>10,}")

        print("\nETL completed successfully.")

    except Exception:
        # Roll back database changes if the ETL fails.
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()