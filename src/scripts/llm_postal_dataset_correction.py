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
import sys
import traceback
from pathlib import Path
from typing import Any

# Add src directory to path
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import polars as pl
from tqdm import tqdm

# Use refactored LLM module
from utils.llm.config import load_config, LLMConfig
from utils.llm.base_client import LLMClient
from utils.llm.schemas.postal_correction import build_complete_prompt
from utils.llm.handlers.markdown_handler import save_markdown_report
from utils.llm.handlers.json_handler import save_json_output, export_corrections_to_csv


class PostalCorrectionGenerator:
    """Generates corrections for unmapped postal code records using LLM."""
    
    def __init__(self, config: LLMConfig):
        """Initialize correction generator with configuration."""
        self.config = config
        self.llm = LLMClient(config)  # Use reusable LLM client
        
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
    
    def validate_and_flag_corrections(self, corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate corrections and add confidence flags.
        
        Args:
            corrections: List of raw corrections from LLM
            
        Returns:
            Validated and flagged corrections
        """
        validated = []
        
        for correction in corrections:
            # Ensure all required fields exist
            if not all(key in correction for key in ["confidence", "flags"]):
                print(f"Warning: Skipping invalid correction: {correction.get('original_value', 'unknown')}")
                continue

            # Filter out redundant corrections (no change)
            original = str(correction.get("original_value", "")).strip()
            corrected = str(correction.get("corrected_value", "")).strip()
            if original and corrected and original.lower() == corrected.lower():
                print(f"Skipping redundant correction (values identical): {original} -> {corrected}")
                continue
            
            # Add LOW_CONFIDENCE flag if below threshold
            confidence = correction.get("confidence", 0.0)
            flags = correction.get("flags", [])
            
            if confidence < self.config.confidence_threshold_flag:
                if "TOO_LOW_CONFIDENCE" not in flags:
                    flags.append("TOO_LOW_CONFIDENCE")
                    correction["flags"] = flags
                # Skip corrections below absolute minimum
                print(f"Skipping low confidence correction: {correction.get('original_value')} → "
                      f"{correction.get('corrected_value')} (confidence: {confidence:.2f})")
                continue
            elif confidence < self.config.confidence_threshold_auto_apply:
                if "LOW_CONFIDENCE" not in flags:
                    flags.append("LOW_CONFIDENCE")
                    correction["flags"] = flags
            
            validated.append(correction)
        
        return validated
    
    def generate_corrections(self, province: str, dry_run: bool = False) -> dict[str, Any]:
        """
        Generate corrections for a province.
        
        Args:
            province: Province name
            dry_run: If True, don't save outputs
            
        Returns:
            Dictionary with correction results and statistics
        """
        print(f"\n{'='*80}")
        print(f"Processing: {province.replace('_', ' ').title()}")
        print(f"{'='*80}\n")
        
        try:
            # Step 1: Load unmapped data
            unmapped_detail, unmapped_pos = self.load_unmapped_data(province)
            
            # Skip if no unmapped records
            if len(unmapped_detail) == 0:
                print("No unmapped detail records - skipping")
                return {"province": province, "status": "skipped", "reason": "no_unmapped_detail"}
            
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
            
            # Step 4: Extract and validate corrections
            raw_corrections = llm_response.get("corrections", [])
            print(f"\nLLM returned {len(raw_corrections)} corrections")
            
            validated_corrections = self.validate_and_flag_corrections(raw_corrections)
            print(f"After validation: {len(validated_corrections)} corrections")
            
            # Categorize by confidence
            high_conf = [c for c in validated_corrections if c.get("confidence", 0) >= self.config.confidence_threshold_auto_apply]
            low_conf = [c for c in validated_corrections if c.get("confidence", 0) < self.config.confidence_threshold_auto_apply]
            
            print(f"  High confidence (confidence >= {self.config.confidence_threshold_auto_apply}): {len(high_conf)}")
            print(f"  Low confidence (confidence < {self.config.confidence_threshold_auto_apply}): {len(low_conf)}")
            
            # Step 5: Save outputs
            print("\n=== Saving Outputs ===")

            # Define output directory for province
            province_output_dir = self.config.output_markdown_dir / province
            province_output_dir.mkdir(parents=True, exist_ok=True)

            # Save markdown report
            markdown_path = save_markdown_report(
                province=province,
                corrections=validated_corrections,
                output_dir=province_output_dir,
                unmapped_detail=unmapped_detail,
                unmapped_pos=unmapped_pos
            )
            print(f"[OK] Markdown: {markdown_path}")

            # Save JSON
            json_path = save_json_output(
                province=province,
                corrections=validated_corrections,
                output_dir=province_output_dir,
                confidence_threshold=self.config.confidence_threshold_auto_apply
            )
            print(f"[OK] JSON: {json_path}")

            # Save diagnostic CSV
            diagnostic_path = province_output_dir / f"{province}_llm_diagnostic.csv"
            export_corrections_to_csv(validated_corrections, diagnostic_path)
            print(f"[OK] Diagnostic CSV: {diagnostic_path}")
            
            # Print summary
            print(f"\n{'='*80}")
            print(f"SUMMARY: {province.replace('_', ' ').title()}")
            print(f"{'='*80}")
            print(f"Total corrections: {len(validated_corrections)}")
            print(f"High confidence: {len(high_conf)}")
            print(f"Low confidence: {len(low_conf)}")
            print(f"{'='*80}\n")
            
            return {
                "province": province,
                "status": "success",
                "total_corrections": len(validated_corrections),
                "high_confidence": len(high_conf),
                "low_confidence": len(low_conf),
                "outputs": {
                    "markdown": str(markdown_path),
                    "json": str(json_path),
                    "diagnostic": str(diagnostic_path)
                }
            }
            
        except Exception as e:
            print(f"\n{'='*80}")
            print(f"ERROR processing {province}")
            print(f"{'='*80}")
            print(traceback.format_exc())
            return {"province": province, "status": "error", "error": str(e)}


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description='LLM-based Postal Code Correction Generator',
        epilog='Uses LLM to analyze unmapped records and generate corrections'
    )
    parser.add_argument('--province', type=str, help='Specific province to process')
    parser.add_argument('--log-dir', type=str, help='Input log directory (overrides config)')
    parser.add_argument('--output-dir', type=str, help='Output directory for markdown/JSON (overrides config)')
    parser.add_argument('--dry-run', action='store_true', help='Test without calling LLM or saving outputs')
    parser.add_argument('--list-provinces', action='store_true', help='List available provinces and exit')

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
            provinces = sorted([
                d.name for d in config.output_log_dir.iterdir()
                if d.is_dir() and (d / f"{d.name}_remain_unmapped_detail.csv").exists()
            ])
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
                print("CAUTION: ALWAYS CHECK THE OUTPUT FROM LLM. YOU SHOULD VALIDATE IT.")
                print("\n[OK] Processing complete!")
            elif result["status"] == "error":
                print(f"\n[FAIL] Processing failed: {result.get('error')}")
                sys.exit(1)
        else:
            # Process all provinces
            provinces = sorted([
                d.name for d in config.output_log_dir.iterdir()
                if d.is_dir() and (d / f"{d.name}_remain_unmapped_detail.csv").exists()
            ])
            
            print(f"\nFound {len(provinces)} provinces to process")
            
            results = []
            for province in tqdm(provinces, desc="Processing provinces"):
                result = generator.generate_corrections(province, dry_run=args.dry_run)
                results.append(result)
            
            # Print final summary
            successful = [r for r in results if r["status"] == "success"]
            failed = [r for r in results if r["status"] == "error"]
            skipped = [r for r in results if r["status"] == "skipped"]
            
            print(f"\n{'='*80}")
            print("FINAL SUMMARY")
            print(f"{'='*80}")
            print(f"Successful: {len(successful)}/{len(provinces)}")
            print(f"Failed: {len(failed)}")
            print(f"Skipped: {len(skipped)}")
            
            if failed:
                print("\nFailed provinces:")
                for r in failed:
                    print(f"  - {r['province']}: {r.get('error', 'unknown error')}")
            
            print(f"{'='*80}\n")
            
    except Exception as e:
        print(f"\nFatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
