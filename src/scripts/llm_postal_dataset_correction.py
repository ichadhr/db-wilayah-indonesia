#!/usr/bin/env python3
"""
LLM-based Postal Code Dataset Correction

This script uses Large Language Models to analyze unmapped postal code records
and generate corrections based on semantic understanding of the detail_keterangan
field, which contains information about administrative changes, name corrections,
and official references.

Usage:
    # Single province
    python src/scripts/llm_postal_dataset_correction.py --province aceh

    # All provinces
    python src/scripts/llm_postal_dataset_correction.py

    # With custom configuration
    python src/scripts/llm_postal_dataset_correction.py --province aceh --dry-run
"""

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import polars as pl
from tqdm import tqdm

# Add src directory to path
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


from utils.llm.base_client import LLMClient

# Use refactored LLM module
from utils.llm.config import LLMConfig, load_config
from utils.llm.handlers.json_handler import export_corrections_to_csv, save_json_output
from utils.llm.handlers.markdown_handler import save_markdown_report
from utils.llm.schemas.postal_correction import build_complete_prompt


class PostalCorrectionGenerator:
    """Generates corrections for unmapped postal code records using LLM."""

    def __init__(self, config: LLMConfig):
        """Initialize correction generator with configuration."""
        self.config = config
        self.llm = LLMClient(config)  # Use factory method for Braintrust integration

    def load_unmapped_data(self, province: str) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        Load unmapped detail and POS records for a province.

        Args:
            province: Province name

        Returns:
            Tuple of (unmapped_detail, unmapped_pos) DataFrames
        """
        province_dir = self.config.output_log_dir / province

        detail_file = province_dir / f"{province}_remain_unmapped_detail.csv"
        pos_file = province_dir / f"{province}_remain_unmapped_pos.csv"

        if not detail_file.exists():
            raise FileNotFoundError(f"Detail file not found: {detail_file}")
        if not pos_file.exists():
            raise FileNotFoundError(f"POS file not found: {pos_file}")

        # Load CSV files
        unmapped_detail = pl.read_csv(detail_file)
        unmapped_pos = pl.read_csv(pos_file)

        print(f"Loaded {len(unmapped_detail):,} unmapped detail records")
        print(f"Loaded {len(unmapped_pos):,} unmapped POS records")

        return unmapped_detail, unmapped_pos

    def generate_corrections(
        self, province: str, dry_run: bool = False
    ) -> dict[str, Any]:
        """
        Generate corrections for a province.

        Args:
            province: Province name
            dry_run: If True, don't save outputs

        Returns:
            Dictionary with correction results and statistics
        """
        print(f"\n{'=' * 80}")
        print(f"Processing: {province.replace('_', ' ').title()}")
        print(f"{'=' * 80}\n")

        try:
            # Step 1: Load unmapped data
            unmapped_detail, unmapped_pos = self.load_unmapped_data(province)

            # Skip if no unmapped records
            if len(unmapped_detail) == 0:
                print("No unmapped detail records - skipping")
                return {
                    "province": province,
                    "status": "skipped",
                    "reason": "no_unmapped_detail",
                }

            # Step 2: Build prompt
            print("\nBuilding LLM prompt...")
            system_prompt, user_prompt, output_schema = build_complete_prompt(
                unmapped_detail, unmapped_pos, province
            )

            if dry_run:
                print("\n[DRY RUN] Would call LLM with:")
                print(f"System prompt length: {len(system_prompt)} chars")
                print(f"User prompt length: {len(user_prompt)} chars")
                return {"province": province, "status": "dry_run"}

            # Step 3: Call LLM using LLMClient
            llm_response = self.llm.call_llm(system_prompt, user_prompt, output_schema)

            # Step 4: Extract raw corrections
            raw_corrections = llm_response.get("corrections", [])
            print(f"\nLLM returned {len(raw_corrections)} raw corrections")

            # Step 5: Save raw output directly
            print("\n=== Saving Raw Output ===")

            # Define output directory for province (relative to project root)
            project_root = Path(__file__).parent.parent.parent
            province_output_dir = (
                project_root / "src" / "datas" / "comparing_pos" / province / "raw"
            )
            province_output_dir.mkdir(parents=True, exist_ok=True)

            # Save raw JSON
            raw_json_path = province_output_dir / f"{province}_raw.json"
            with open(raw_json_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"corrections": raw_corrections}, f, ensure_ascii=False, indent=2
                )
            print(f"[OK] Raw JSON: {raw_json_path}")

            # Save raw CSV - FINAL FORMAT: Flatten new structure
            raw_csv_path = province_output_dir / f"{province}_raw.csv"
            if raw_corrections:
                # Flatten the final format: each correction becomes separate row
                flattened_corrections = []
                for record_id, record in enumerate(raw_corrections, 1):
                    original = record["original_pos_data"]

                    # Create a row for each correction in the array
                    for correction in record["corrections"]:
                        flat_correction = {
                            "id": record_id,
                            "province": original["province"],
                            "regency_city": original["regency_city"],
                            "original_kecamatan": original["kecamatan"],
                            "original_desa_kelurahan": original["desa_kelurahan"],
                            "correction_field": correction["field"],
                            "corrected_value": correction["corrected_value"],
                            "reasoning": correction["reasoning"],
                            "confidence": correction["confidence"],
                            "references": record["references"],
                            "flags": ", ".join(record["flags"])
                            if isinstance(record["flags"], list)
                            else record["flags"],
                            "evidence_type": record["evidence_type"],
                        }
                        flattened_corrections.append(flat_correction)

                # Create DataFrame with proper column order
                if flattened_corrections:
                    df = pl.DataFrame(flattened_corrections)
                    # Reorder columns to match expected CSV format
                    column_order = [
                        "id",
                        "province",
                        "regency_city",
                        "original_kecamatan",
                        "original_desa_kelurahan",
                        "correction_field",
                        "corrected_value",
                        "reasoning",
                        "confidence",
                        "references",
                        "flags",
                        "evidence_type",
                    ]
                    df = df.select([col for col in column_order if col in df.columns])
                    df.write_csv(raw_csv_path)
            print(f"[OK] Raw CSV: {raw_csv_path}")

            # Print summary
            print(f"\n{'=' * 80}")
            print(f"SUMMARY: {province.replace('_', ' ').title()}")
            print(f"{'=' * 80}")
            print(f"Total raw corrections: {len(raw_corrections)}")
            print(f"Raw JSON saved: {raw_json_path}")
            print(f"Raw CSV saved: {raw_csv_path}")
            print(f"{'=' * 80}\n")

            return {
                "province": province,
                "status": "success",
                "total_raw_corrections": len(raw_corrections),
                "outputs": {"raw_json": str(raw_json_path)},
            }

        except Exception as e:
            print(f"\n{'=' * 80}")
            print(f"ERROR processing {province}")
            print(f"{'=' * 80}")
            print(traceback.format_exc())
            return {"province": province, "status": "error", "error": str(e)}


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="LLM-based Postal Code Correction Generator",
        epilog="Uses LLM to analyze unmapped records and generate corrections",
    )
    parser.add_argument("--province", type=str, help="Specific province to process")
    parser.add_argument(
        "--log-dir", type=str, help="Input log directory (overrides config)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for markdown/JSON (overrides config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without calling LLM or saving outputs",
    )
    parser.add_argument(
        "--list-provinces",
        action="store_true",
        help="List available provinces and exit",
    )

    args = parser.parse_args()

    # Determine project root for path resolution
    project_root = Path(__file__).parent.parent.parent

    try:
        # Load configuration
        print("Loading LLM configuration...")
        config = load_config(dry_run=args.dry_run)
        print(f"[OK] Provider: {config.llm_provider}")
        print(f"[OK] Model: {config.llm_model}")

        # Override config with CLI args, resolving paths relative to project root
        if args.log_dir:
            config.output_log_dir = project_root / args.log_dir
        if args.output_dir:
            config.output_markdown_dir = project_root / args.output_dir
            config.output_json_dir = project_root / args.output_dir

        # List provinces if requested
        if args.list_provinces:
            provinces = sorted(
                [
                    d.name
                    for d in config.output_log_dir.iterdir()
                    if d.is_dir()
                    and (d / f"{d.name}_remain_unmapped_detail.csv").exists()
                ]
            )
            print(f"\nFound {len(provinces)} provinces with unmapped data:")
            for province in provinces:
                print(f"  - {province}")
            return

        # Initialize generator
        generator = PostalCorrectionGenerator(config)

        if args.province:
            # Process single province
            result = generator.generate_corrections(args.province, dry_run=args.dry_run)

            if result["status"] == "success":
                print(
                    "CAUTION: ALWAYS CHECK THE OUTPUT FROM LLM. YOU SHOULD VALIDATE IT."
                )
                print("\n[OK] Processing complete!")
            elif result["status"] == "error":
                print(f"\n[FAIL] Processing failed: {result.get('error')}")
                sys.exit(1)
        else:
            # Process all provinces
            provinces = sorted(
                [
                    d.name
                    for d in config.output_log_dir.iterdir()
                    if d.is_dir()
                    and (d / f"{d.name}_remain_unmapped_detail.csv").exists()
                ]
            )

            print(f"\nFound {len(provinces)} provinces to process")

            results = []
            for province in tqdm(provinces, desc="Processing provinces"):
                result = generator.generate_corrections(province, dry_run=args.dry_run)
                results.append(result)

            # Print final summary
            successful = [r for r in results if r["status"] == "success"]
            failed = [r for r in results if r["status"] == "error"]
            skipped = [r for r in results if r["status"] == "skipped"]

            print(f"\n{'=' * 80}")
            print("FINAL SUMMARY")
            print(f"{'=' * 80}")
            print(f"Successful: {len(successful)}/{len(provinces)}")
            print(f"Failed: {len(failed)}")
            print(f"Skipped: {len(skipped)}")

            if failed:
                print("\nFailed provinces:")
                for r in failed:
                    print(f"  - {r['province']}: {r.get('error', 'unknown error')}")

            print(f"{'=' * 80}\n")

    except Exception as e:
        print(f"\nFatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
