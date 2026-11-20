
from etl import DB_CONFIG

from data_quality.quality_engine import run_global_quality_engine

from monitoring.run_tracker import (
    create_run,
    finish_run,
    log_error,
    save_quality_results,
)


def main():

    print("\nStarting monitored Data Quality Engine...")

    if not DB_CONFIG["password"]:
        raise ValueError(
            "POSTGRES_PASSWORD is missing from your .env file."
        )

    # Create a separate monitoring execution.
    monitor_connection, run_id = create_run(
        DB_CONFIG,
        pipeline_name="PubMed Global Data Quality",
        source_name="Cleaned CSV files + Data Warehouse",
    )

    try:
        print(f"Monitoring run ID: {run_id}")

        # 1. Execute all quality checks.
        results, summary = run_global_quality_engine()

        # 2. Save all quality results in PostgreSQL.
        saved_count = save_quality_results(
            monitor_connection,
            run_id,
            results,
        )

        # 3. Determine execution status.
        if (
            summary["warning_checks"] == 0
            and summary["failed_checks"] == 0
            and summary["error_checks"] == 0
        ):
            status = "SUCCESS"
        else:
            status = "PARTIAL"

        # Number of source records evaluated.
        extracted_count = summary["dataset_records"]

        # Number of quality checks saved.
        loaded_count = saved_count

        # No source records are rejected by this engine.
        rejected_count = 0

        # 4. Update monitoring execution.
        finish_run(
            monitor_connection,
            run_id,
            status=status,
            extracted_records=extracted_count,
            loaded_records=loaded_count,
            rejected_records=rejected_count,
        )

        print("\nQUALITY RESULTS SAVED")
        print(f"Run ID             : {run_id}")
        print(f"Checks saved       : {saved_count}")
        print(f"Execution status   : {status}")

        # 5. Display detailed results.
        print("\nDETAILED RESULTS")
        print("-" * 65)

        print(
            results[
                [
                    "category",
                    "check_name",
                    "failed_records",
                    "status",
                ]
            ].to_string(index=False)
        )

    except Exception as error:

        print(f"\nData Quality Engine failed: {error}")

        try:
            log_error(
                monitor_connection,
                run_id,
                error,
            )

            finish_run(
                monitor_connection,
                run_id,
                status="FAILED",
                error_message=str(error),
            )

        except Exception as monitoring_error:
            print(
                "Could not update monitoring: "
                f"{monitoring_error}"
            )

        raise

    finally:
        monitor_connection.close()


if __name__ == "__main__":
    main()
