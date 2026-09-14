
from pathlib import Path
import time
import argparse

import streamlit as st

from services.realestate_monitor import (
    init_db,
    run_monitoring_once,
)

BASE_DIR = Path(__file__).resolve().parent

try:
    INTERVAL_MINUTES = int(
        st.secrets["realestate"].get(
            "MONITOR_INTERVAL_MINUTES",
            "60",
        )
    )
except Exception:
    INTERVAL_MINUTES = 60


def main():
    init_db(BASE_DIR)

    print(
        f"[부동산 scheduler] "
        f"{INTERVAL_MINUTES}분 간격"
    )

    while True:
        try:
            result = run_monitoring_once(
                BASE_DIR
            )
            print(
                "[monitor result]",
                result,
            )

        except Exception as e:
            print(
                "[monitor error]",
                repr(e),
            )

        time.sleep(
            INTERVAL_MINUTES * 60
        )


def run_once():
    """Run one safe monitoring cycle for GitHub Actions."""
    init_db(BASE_DIR)
    result = run_monitoring_once(BASE_DIR)
    print("[monitor result]", result)
    if result["errors"]:
        raise RuntimeError("; ".join(result["errors"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run_once() if args.once else main()
