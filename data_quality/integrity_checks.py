
from pathlib import Path
import json
import subprocess
import pandas as pd


# Project configuration
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "quality_reports"

CONTAINER = "pubmed_dw_db"
DATABASE = "pubmed_dw"
DB_USER = "pubmed_user"
SCHEMA = "dw"


def execute_count_query(query):
    """
    Execute a SQL COUNT query inside the PostgreSQL Docker container.
    Returns one integer.
    """

    command = [
        "docker", "exec", CONTAINER,
        "psql",
        "-X",
        "-q",
        "-A",
        "-t",
        "-v", "ON_ERROR_STOP=1",
        "-U", DB_USER,
        "-d", DATABASE,
        "-c", query
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.returncode != 0:
        raise RuntimeError(
            "PostgreSQL query failed:\n"
            + result.stderr
            + "\nQuery:\n"
            + query
        )

    output = result.stdout.strip()

    try:
        return int(output)
    except ValueError:
        raise RuntimeError(
            f"Expected an integer from PostgreSQL, received: {output!r}"
        )


def run_integrity_checks():
    """Execute integrity checks on the PostgreSQL data warehouse."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    def add_check(
        check_name,
        table_name,
        total_query,
        failed_query,
        severity="FAIL",
        details_label="problematic records"
    ):
        total = execute_count_query(total_query)
        failed = execute_count_query(failed_query)

        if failed == 0:
            status = "PASS"
        else:
            status = severity

        results.append({
            "check_name": check_name,
            "table_name": table_name,
            "total_records": total,
            "failed_records": failed,
            "status": status,
            "details": f"{failed} {details_label}"
        })

    # --------------------------------------------------
    # 1. Fact table: primary key and foreign keys
    # --------------------------------------------------

    add_check(
        "fact_article_pmid_uniqueness",
        "fact_article",
        f"SELECT COUNT(*) FROM {SCHEMA}.fact_article",
        f"""
        SELECT COUNT(*) FROM (
            SELECT pmid
            FROM {SCHEMA}.fact_article
            GROUP BY pmid
            HAVING COUNT(*) > 1
        ) duplicates
        """
    )

    add_check(
        "fact_article_pmid_null",
        "fact_article",
        f"SELECT COUNT(*) FROM {SCHEMA}.fact_article",
        f"""
        SELECT COUNT(*)
        FROM {SCHEMA}.fact_article
        WHERE pmid IS NULL OR TRIM(pmid) = ''
        """
    )

    add_check(
        "fact_article_year_orphan",
        "fact_article",
        f"SELECT COUNT(*) FROM {SCHEMA}.fact_article",
        f"""
        SELECT COUNT(*)
        FROM {SCHEMA}.fact_article f
        WHERE f.year_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {SCHEMA}.dim_year y
              WHERE y.year_id = f.year_id
          )
        """
    )

    add_check(
        "fact_article_journal_orphan",
        "fact_article",
        f"SELECT COUNT(*) FROM {SCHEMA}.fact_article",
        f"""
        SELECT COUNT(*)
        FROM {SCHEMA}.fact_article f
        WHERE f.journal_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {SCHEMA}.dim_journal j
              WHERE j.journal_id = f.journal_id
          )
        """
    )

    # Missing year and journal are warnings because
    # three such articles are already documented.
    add_check(
        "fact_article_missing_year",
        "fact_article",
        f"SELECT COUNT(*) FROM {SCHEMA}.fact_article",
        f"""
        SELECT COUNT(*)
        FROM {SCHEMA}.fact_article
        WHERE year_id IS NULL
        """,
        severity="WARNING",
        details_label="articles without year_id"
    )

    add_check(
        "fact_article_missing_journal",
        "fact_article",
        f"SELECT COUNT(*) FROM {SCHEMA}.fact_article",
        f"""
        SELECT COUNT(*)
        FROM {SCHEMA}.fact_article
        WHERE journal_id IS NULL
        """,
        severity="WARNING",
        details_label="articles without journal_id"
    )

    # --------------------------------------------------
    # 2. Dimension primary keys
    # --------------------------------------------------

    dimensions = {
        "dim_year": "year_id",
        "dim_journal": "journal_id",
        "dim_author": "author_id",
        "dim_keyword": "keyword_id",
        "dim_mesh_term": "mesh_term_id",
        "dim_publication_type": "publication_type_id",
    }

    for table, key in dimensions.items():

        add_check(
            f"{table}_{key}_null",
            table,
            f"SELECT COUNT(*) FROM {SCHEMA}.{table}",
            f"""
            SELECT COUNT(*)
            FROM {SCHEMA}.{table}
            WHERE {key} IS NULL
            """
        )

        add_check(
            f"{table}_{key}_uniqueness",
            table,
            f"SELECT COUNT(*) FROM {SCHEMA}.{table}",
            f"""
            SELECT COUNT(*) FROM (
                SELECT {key}
                FROM {SCHEMA}.{table}
                GROUP BY {key}
                HAVING COUNT(*) > 1
            ) duplicates
            """
        )

    # --------------------------------------------------
    # 3. Bridge table foreign keys and duplicates
    # --------------------------------------------------

    bridges = {
        "bridge_article_author": {
            "dimension_table": "dim_author",
            "dimension_key": "author_id",
        },
        "bridge_article_keyword": {
            "dimension_table": "dim_keyword",
            "dimension_key": "keyword_id",
        },
        "bridge_article_mesh": {
            "dimension_table": "dim_mesh_term",
            "dimension_key": "mesh_term_id",
        },
        "bridge_article_publication_type": {
            "dimension_table": "dim_publication_type",
            "dimension_key": "publication_type_id",
        },
    }

    for bridge, config in bridges.items():

        dimension_table = config["dimension_table"]
        dimension_key = config["dimension_key"]

        # PMID must exist in fact_article.
        add_check(
            f"{bridge}_article_orphan",
            bridge,
            f"SELECT COUNT(*) FROM {SCHEMA}.{bridge}",
            f"""
            SELECT COUNT(*)
            FROM {SCHEMA}.{bridge} b
            WHERE b.pmid IS NULL
               OR NOT EXISTS (
                   SELECT 1
                   FROM {SCHEMA}.fact_article f
                   WHERE f.pmid = b.pmid
               )
            """
        )

        # Dimension ID must exist in its dimension.
        add_check(
            f"{bridge}_dimension_orphan",
            bridge,
            f"SELECT COUNT(*) FROM {SCHEMA}.{bridge}",
            f"""
            SELECT COUNT(*)
            FROM {SCHEMA}.{bridge} b
            WHERE b.{dimension_key} IS NULL
               OR NOT EXISTS (
                   SELECT 1
                   FROM {SCHEMA}.{dimension_table} d
                   WHERE d.{dimension_key} = b.{dimension_key}
               )
            """
        )

        # Each article-dimension association should be unique.
        add_check(
            f"{bridge}_association_uniqueness",
            bridge,
            f"SELECT COUNT(*) FROM {SCHEMA}.{bridge}",
            f"""
            SELECT COUNT(*) FROM (
                SELECT pmid, {dimension_key}
                FROM {SCHEMA}.{bridge}
                GROUP BY pmid, {dimension_key}
                HAVING COUNT(*) > 1
            ) duplicates
            """
        )

    # --------------------------------------------------
    # 4. Export reports
    # --------------------------------------------------

    results_df = pd.DataFrame(results)

    csv_path = OUTPUT_DIR / "database_integrity_report.csv"
    json_path = OUTPUT_DIR / "database_integrity_report.json"

    results_df.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig"
    )

    report = {
        "database": DATABASE,
        "schema": SCHEMA,
        "total_checks": len(results_df),
        "passed_checks": int(
            (results_df["status"] == "PASS").sum()
        ),
        "warning_checks": int(
            (results_df["status"] == "WARNING").sum()
        ),
        "failed_checks": int(
            (results_df["status"] == "FAIL").sum()
        ),
        "results": results_df.to_dict(orient="records")
    }

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    return results_df
