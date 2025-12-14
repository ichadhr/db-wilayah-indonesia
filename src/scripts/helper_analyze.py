#!/usr/bin/env python3
"""
Script to count rows in {province}_remain_unmapped_detail.csv files
for each province in src/log/ directory.
"""

import os

import polars as pl


def count_detail_unmapped_rows():
    """Count rows in remain_unmapped_detail.csv for each province."""
    log_dir = "log"

    if not os.path.exists(log_dir):
        print(f"Log directory {log_dir} does not exist.")
        return

    provinces = [
        d for d in os.listdir(log_dir) if os.path.isdir(os.path.join(log_dir, d))
    ]

    total_rows = 0
    province_counts = {}

    for province in sorted(provinces):
        file_path = os.path.join(
            log_dir, province, f"{province}_remain_unmapped_detail.csv"
        )

        if os.path.exists(file_path):
            try:
                df = pl.read_csv(file_path)
                count = df.height
                province_counts[province] = count
                total_rows += count
                print(f"{province}: {count} rows")
            except Exception as e:
                print(f"{province}: Error reading file - {e}")
        else:
            province_counts[province] = 0
            print(f"{province}: 0 rows (file not found)")

    print(f"\nTotal unmapped detail rows across all provinces: {total_rows}\n")


def count_pos_unmapped_rows():
    """Count rows in remain_unmapped_pos.csv for each province."""
    log_dir = "log"

    if not os.path.exists(log_dir):
        print(f"Log directory {log_dir} does not exist.")
        return

    provinces = [
        d for d in os.listdir(log_dir) if os.path.isdir(os.path.join(log_dir, d))
    ]

    total_rows = 0
    province_counts = {}

    for province in sorted(provinces):
        file_path = os.path.join(
            log_dir, province, f"{province}_remain_unmapped_pos.csv"
        )

        if os.path.exists(file_path):
            try:
                df = pl.read_csv(file_path)
                count = df.height
                province_counts[province] = count
                total_rows += count
                print(f"{province}: {count} rows")
            except Exception as e:
                print(f"{province}: Error reading file - {e}")
        else:
            province_counts[province] = 0
            print(f"{province}: 0 rows (file not found)")

    print(f"\nTotal unmapped pos rows across all provinces: {total_rows}\n")


def analyze_detail_keterangan():
    """Collect and deduplicate detail_keterangan from all provinces, save to CSV."""
    from pathlib import Path

    log_dir = Path("log")

    if not log_dir.exists():
        print(f"Log directory {log_dir} does not exist.")
        return

    all_keterangan = []
    provinces = [d for d in log_dir.iterdir() if d.is_dir()]

    for province_dir in sorted(provinces):
        file_path = province_dir / f"{province_dir.name}_remain_unmapped_detail.csv"
        if file_path.exists():
            try:
                df = pl.read_csv(file_path)
                if "detail_keterangan" in df.columns:
                    keterangan_list = (
                        df.select("detail_keterangan").unique().to_series().to_list()
                    )
                    all_keterangan.extend(keterangan_list)
                print(f"{province_dir.name}: Loaded and extracted detail_keterangan")
            except Exception as e:
                print(f"{province_dir.name}: Error - {e}")
        else:
            print(f"{province_dir.name}: File not found")

    # Deduplicate
    unique_keterangan = list(set(all_keterangan))

    # Save to CSV
    output_df = pl.DataFrame({"detail_keterangan": unique_keterangan})
    output_file = log_dir / "unique_detail_keterangan.csv"
    output_df.write_csv(output_file)
    print(
        f"Saved {len(unique_keterangan)} unique detail_keterangan entries to {output_file}"
    )


if __name__ == "__main__":
    count_detail_unmapped_rows()
    count_pos_unmapped_rows()
    analyze_detail_keterangan()
