
import psycopg2


def create_run(db_config, pipeline_name, source_name):
    """Create a monitoring record before starting the ETL."""

    connection = psycopg2.connect(**db_config)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO monitoring.etl_runs (
                    pipeline_name,
                    source_name,
                    status
                )
                VALUES (%s, %s, 'RUNNING')
                RETURNING run_id;
                """,
                (pipeline_name, source_name),
            )

            run_id = cursor.fetchone()[0]

        connection.commit()
        return connection, run_id

    except Exception:
        connection.rollback()
        connection.close()
        raise


def finish_run(
    connection,
    run_id,
    status,
    extracted_records=0,
    loaded_records=0,
    rejected_records=0,
    error_message=None,
):
    """Update the monitoring record when the ETL finishes."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE monitoring.etl_runs
            SET
                end_time = CURRENT_TIMESTAMP,
                duration_seconds = EXTRACT(
                    EPOCH FROM (CURRENT_TIMESTAMP - start_time)
                ),
                status = %s,
                extracted_records = %s,
                loaded_records = %s,
                rejected_records = %s,
                error_message = %s
            WHERE run_id = %s;
            """,
            (
                status,
                extracted_records,
                loaded_records,
                rejected_records,
                error_message,
                run_id,
            ),
        )

    connection.commit()


def log_error(connection, run_id, error):
    """Store an ETL exception in monitoring.etl_errors."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO monitoring.etl_errors (
                run_id,
                error_type,
                error_message
            )
            VALUES (%s, %s, %s);
            """,
            (
                run_id,
                type(error).__name__,
                str(error),
            ),
        )

    connection.commit()


def save_quality_results(connection, run_id, results):
    """Save all Data Quality checks in PostgreSQL."""

    rows = []

    for _, row in results.iterrows():
        def clean_value(value):
            if value is None:
                return None

            try:
                if __import__("pandas").isna(value):
                    return None
            except (TypeError, ValueError):
                pass

            if hasattr(value, "item"):
                return value.item()

            return value

        rows.append((
            str(run_id),
            clean_value(row.get("category")),
            clean_value(row.get("check_name")),
            clean_value(row.get("table_name")),
            clean_value(row.get("column_name")),
            clean_value(row.get("total_records")),
            clean_value(row.get("failed_records")),
            clean_value(row.get("quality_score")),
            clean_value(row.get("status")),
            clean_value(row.get("details")),
        ))

    if not rows:
        return 0

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO monitoring.data_quality_results (
                run_id,
                category,
                check_name,
                table_name,
                column_name,
                total_records,
                failed_records,
                quality_score,
                status,
                details
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            rows,
        )

    connection.commit()

    return len(rows)

