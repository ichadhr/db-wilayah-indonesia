"""
TRUE Cascading Hierarchical Matching Script

This script implements strict hierarchical filtering where each administrative 
level must independently meet its threshold before proceeding to the next level.

Key differences from scoring_hierarchical.py:
- Hard gates at each level (no compensation between levels)
- 1-to-1 matching (both detail and POS side)
- No match categories (just match/no-match)
- Early termination when any gate fails
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Add src directory to path for imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import polars as pl
from recordlinkage import compare
from utils.text_utils import normalize_for_matching

# Thresholds based on empirical validation
PROVINCE_THRESHOLD = 0.95
KABUPATEN_THRESHOLD = 0.95
KECAMATAN_THRESHOLD = 0.75
KELURAHAN_THRESHOLD = 0.70
OVERALL_THRESHOLD = 0.80


def load_join_data(province_dir: Path | str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Load detail and pos dataframes from separate CSV files.
    
    Args:
        province_dir: Path to the province directory containing detail_join.csv and pos_join.csv
        
    Returns:
        Tuple of (detail_df, pos_df)
    """
    province_dir = Path(province_dir)
    detail_csv = province_dir / f"{province_dir.name}_detail_join.csv"
    pos_csv = province_dir / f"{province_dir.name}_pos_join.csv"
    
    print(f"Loading data from {province_dir}...")
    
    # Load detail records
    detail_df = pl.read_csv(detail_csv, encoding='utf8-lossy')
    print(f"Loaded {len(detail_df)} detail records from {detail_csv.name}")
    
    # Load pos records
    pos_df = pl.read_csv(pos_csv, encoding='utf8-lossy')
    print(f"Loaded {len(pos_df)} pos records from {pos_csv.name}")
    
    return detail_df, pos_df


def fuzzy_similarity(str1: str, str2: str, algorithm: str = 'jarowinkler') -> float:
    """
    Calculate fuzzy string similarity using Jaro-Winkler.
    
    Args:
        str1: First string
        str2: Second string
        algorithm: Similarity algorithm (default: jarowinkler)
        
    Returns:
        Similarity score between 0 and 1
    """
    if not str1 or not str2:
        return 0.0
    
    # Use jellyfish for Jaro-Winkler
    try:
        import jellyfish
        if algorithm == 'jarowinkler':
            return jellyfish.jaro_winkler_similarity(str1, str2)
        else:
            return jellyfish.jaro_similarity(str1, str2)
    except ImportError:
        # Fallback to simple character ratio if jellyfish not available
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1, str2).ratio()


def cascading_match(
    detail_df: pl.DataFrame, 
    pos_df: pl.DataFrame
) -> List[Dict[str, Any]]:
    """
    Perform TRUE cascading hierarchical matching with hard gates.
    
    Each level must pass its threshold independently. No compensation allowed.
    
    Args:
        detail_df: Detail dataset
        pos_df: POS dataset
        
    Returns:
        List of match dictionaries
    """
    matches = []
    
    print(f"\n=== TRUE Cascading Matching ===")
    print(f"Thresholds: Province={PROVINCE_THRESHOLD}, Kabupaten={KABUPATEN_THRESHOLD}, "
          f"Kecamatan={KECAMATAN_THRESHOLD}, Kelurahan={KELURAHAN_THRESHOLD}, Overall={OVERALL_THRESHOLD}")
    
    # Convert to list of dicts for easier processing
    detail_records = detail_df.to_dicts()
    pos_records = pos_df.to_dicts()
    
    total_pairs = len(detail_records) * len(pos_records)
    print(f"Total possible pairs: {total_pairs:,}")
    
    # Track pairs at each gate
    gate_stats = {
        'total': total_pairs,
        'after_province': 0,
        'after_kabupaten': 0,
        'after_kecamatan': 0,
        'after_kelurahan': 0,
        'after_overall': 0
    }
    
    # Process each detail-POS combination
    for detail_idx, detail_row in enumerate(detail_records):
        if (detail_idx + 1) % 100 == 0:
            print(f"Processing detail record {detail_idx + 1}/{len(detail_records)}...")
        
        for pos_idx, pos_row in enumerate(pos_records):
            # Normalize fields
            detail_prov_norm = normalize_for_matching(str(detail_row.get('provinsi', '')), 'province')
            pos_prov_norm = normalize_for_matching(str(pos_row.get('provinsi', '')), 'province')
            
            detail_kab_norm = normalize_for_matching(str(detail_row.get('kabupaten_kota', '')), 'kabupaten')
            pos_kab_norm = normalize_for_matching(str(pos_row.get('kabupaten_kota', '')), 'kabupaten')
            
            detail_kec_norm = normalize_for_matching(str(detail_row.get('kecamatan', '')), 'kecamatan')
            pos_kec_norm = normalize_for_matching(str(pos_row.get('kecamatan', '')), 'kecamatan')
            
            detail_kel_norm = normalize_for_matching(str(detail_row.get('kelurahan_desa', '')), 'kelurahan')
            pos_kel_norm = normalize_for_matching(str(pos_row.get('kelurahan_desa', '')), 'kelurahan')
            
            # ===== GATE 1: Province =====
            prov_sim = fuzzy_similarity(detail_prov_norm, pos_prov_norm)
            if prov_sim < PROVINCE_THRESHOLD:
                continue  # REJECT - next POS
            gate_stats['after_province'] += 1
            
            # ===== GATE 2: Kabupaten =====
            kab_sim = fuzzy_similarity(detail_kab_norm, pos_kab_norm)
            if kab_sim < KABUPATEN_THRESHOLD:
                continue  # REJECT - next POS
            gate_stats['after_kabupaten'] += 1
            
            # ===== GATE 3: Kecamatan (CRITICAL) =====
            kec_sim = fuzzy_similarity(detail_kec_norm, pos_kec_norm)
            if kec_sim < KECAMATAN_THRESHOLD:
                continue  # REJECT - wrong postal zone
            gate_stats['after_kecamatan'] += 1
            
            # ===== GATE 4: Kelurahan =====
            kel_sim = fuzzy_similarity(detail_kel_norm, pos_kel_norm)
            if kel_sim < KELURAHAN_THRESHOLD:
                continue  # REJECT - next POS
            gate_stats['after_kelurahan'] += 1
            
            # ===== GATE 5: Overall Confidence =====
            overall_conf = 0.4 * kec_sim + 0.6 * kel_sim
            if overall_conf < OVERALL_THRESHOLD:
                continue  # REJECT - borderline quality
            gate_stats['after_overall'] += 1
            
            # ===== PASSED ALL GATES =====
            matches.append({
                # Detail side
                'detail_kode_kelurahan': str(detail_row.get('kode_kelurahan', '')),
                'detail_provinsi': str(detail_row.get('provinsi', '')),
                'detail_kabupaten_kota': str(detail_row.get('kabupaten_kota', '')),
                'detail_kecamatan': str(detail_row.get('kecamatan', '')),
                'detail_kelurahan_desa': str(detail_row.get('kelurahan_desa', '')),
                
                # Similarity scores
                'provinsi_similarity': prov_sim,
                'kabupaten_similarity': kab_sim,
                'kecamatan_similarity': kec_sim,
                'kelurahan_similarity': kel_sim,
                'overall_confidence': overall_conf,
                
                # POS side
                'pos_provinsi': str(pos_row.get('provinsi', '')),
                'pos_kabupaten_kota': str(pos_row.get('kabupaten_kota', '')),
                'pos_kecamatan': str(pos_row.get('kecamatan', '')),
                'pos_kelurahan_desa': str(pos_row.get('kelurahan_desa', '')),
                'pos_kodepos': str(pos_row.get('kodepos', '')),
                
                # Indices for deduplication
                'detail_idx': detail_idx,
                'pos_idx': pos_idx
            })
    
    # Print gate statistics
    print(f"\n=== Gate Statistics ===")
    print(f"Total pairs: {gate_stats['total']:,}")
    print(f"After Province gate (>={PROVINCE_THRESHOLD}): {gate_stats['after_province']:,} "
          f"({100*gate_stats['after_province']/gate_stats['total']:.1f}%)")
    print(f"After Kabupaten gate (>={KABUPATEN_THRESHOLD}): {gate_stats['after_kabupaten']:,} "
          f"({100*gate_stats['after_kabupaten']/gate_stats['total']:.1f}%)")
    print(f"After Kecamatan gate (>={KECAMATAN_THRESHOLD}): {gate_stats['after_kecamatan']:,} "
          f"({100*gate_stats['after_kecamatan']/gate_stats['total']:.1f}%)")
    print(f"After Kelurahan gate (>={KELURAHAN_THRESHOLD}): {gate_stats['after_kelurahan']:,} "
          f"({100*gate_stats['after_kelurahan']/gate_stats['total']:.1f}%)")
    print(f"After Overall gate (>={OVERALL_THRESHOLD}): {gate_stats['after_overall']:,} "
          f"({100*gate_stats['after_overall']/gate_stats['total']:.1f}%)")
    
    return matches


def deduplicate_1to1(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Perform strict 1-to-1 deduplication on both sides.
    
    Each detail record can match at most one POS record.
    Each POS record can match at most one detail record.
    
    Args:
        matches: List of match dictionaries
        
    Returns:
        Deduplicated list of matches
    """
    if not matches:
        return []
    
    # Sort by overall_confidence descending
    sorted_matches = sorted(matches, key=lambda x: x['overall_confidence'], reverse=True)
    
    used_detail = set()
    used_pos = set()
    final_matches = []
    
    for match in sorted_matches:
        detail_idx = match['detail_idx']
        pos_idx = match['pos_idx']
        
        # Check if already used
        if detail_idx in used_detail or pos_idx in used_pos:
            continue  # Skip this match
        
        # Add to final matches
        final_matches.append(match)
        used_detail.add(detail_idx)
        used_pos.add(pos_idx)
    
    print(f"\n=== Deduplication (1-to-1) ===")
    print(f"Before deduplication: {len(matches)} matches")
    print(f"After deduplication: {len(final_matches)} matches")
    print(f"Unique detail records matched: {len(used_detail)}")
    print(f"Unique POS records matched: {len(used_pos)}")
    
    return final_matches


def create_unmatched_records(
    detail_df: pl.DataFrame,
    matched_detail_indices: set
) -> List[Dict[str, Any]]:
    """
    Create records for unmatched detail entries.
    
    Args:
        detail_df: Original detail dataframe
        matched_detail_indices: Set of detail indices that were matched
        
    Returns:
        List of unmatched record dictionaries
    """
    unmatched = []
    detail_records = detail_df.to_dicts()
    
    for idx, detail_row in enumerate(detail_records):
        if idx not in matched_detail_indices:
            unmatched.append({
                # Detail side
                'detail_kode_kelurahan': str(detail_row.get('kode_kelurahan', '')),
                'detail_provinsi': str(detail_row.get('provinsi', '')),
                'detail_kabupaten_kota': str(detail_row.get('kabupaten_kota', '')),
                'detail_kecamatan': str(detail_row.get('kecamatan', '')),
                'detail_kelurahan_desa': str(detail_row.get('kelurahan_desa', '')),
                
                # Similarity scores (all zero for unmatched)
                'provinsi_similarity': 0.0,
                'kabupaten_similarity': 0.0,
                'kecamatan_similarity': 0.0,
                'kelurahan_similarity': 0.0,
                'overall_confidence': 0.0,
                
                # POS side (empty for unmatched)
                'pos_provinsi': '',
                'pos_kabupaten_kota': '',
                'pos_kecamatan': '',
                'pos_kelurahan_desa': '',
                'pos_kodepos': '',
                
                # Indices
                'detail_idx': idx,
                'pos_idx': -1
            })
    
    return unmatched


def create_unmatched_pos_records(
    pos_df: pl.DataFrame,
    matched_pos_indices: set
) -> List[Dict[str, Any]]:
    """
    Create records for unmatched POS entries.
    
    Args:
        pos_df: Original POS dataframe
        matched_pos_indices: Set of POS indices that were matched
        
    Returns:
        List of unmatched POS record dictionaries
    """
    unmatched = []
    pos_records = pos_df.to_dicts()
    
    for idx, pos_row in enumerate(pos_records):
        if idx not in matched_pos_indices:
            unmatched.append({
                # POS side
                'pos_provinsi': str(pos_row.get('provinsi', '')),
                'pos_kabupaten_kota': str(pos_row.get('kabupaten_kota', '')),
                'pos_kecamatan': str(pos_row.get('kecamatan', '')),
                'pos_kelurahan_desa': str(pos_row.get('kelurahan_desa', '')),
                'pos_kodepos': str(pos_row.get('kodepos', '')),
            })
    
    return unmatched


def save_unmatched_pos(
    unmatched_pos: List[Dict[str, Any]],
    output_dir: Path,
    province_name: str
):
    """
    Save unmatched POS records to separate CSV file.
    
    Args:
        unmatched_pos: List of unmatched POS dictionaries
        output_dir: Directory to save output files
        province_name: Name of province for file naming
    """
    if not unmatched_pos:
        print("No unmatched POS records to save.")
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert to DataFrame
    unmatched_df = pl.DataFrame(unmatched_pos)
    
    # Save to CSV
    output_file = output_dir / f"{province_name}_cascading_matches_remain.csv"
    unmatched_df.write_csv(output_file)
    print(f"Saved {len(unmatched_df)} unmatched POS records to {output_file}")


def save_results(
    matched_records: List[Dict[str, Any]], 
    unmatched_records: List[Dict[str, Any]],
    output_dir: Path, 
    province_name: str
):
    """
    Save matching results to CSV file.
    
    Args:
        matched_records: List of matched record dictionaries
        unmatched_records: List of unmatched record dictionaries
        output_dir: Directory to save output files
        province_name: Name of province for file naming
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert to Polars DataFrames separately
    if matched_records:
        matched_df = pl.DataFrame(matched_records).drop(['detail_idx', 'pos_idx'])
    else:
        matched_df = pl.DataFrame()
    
    if unmatched_records:
        unmatched_df = pl.DataFrame(unmatched_records).drop(['detail_idx', 'pos_idx'])
    else:
        unmatched_df = pl.DataFrame()
    
    # Combine if both exist
    if len(matched_df) > 0 and len(unmatched_df) > 0:
        results_df = pl.concat([matched_df, unmatched_df], how='vertical')
    elif len(matched_df) > 0:
        results_df = matched_df
    elif len(unmatched_df) > 0:
        results_df = unmatched_df
    else:
        results_df = pl.DataFrame()
    
    # Reorder columns if dataframe is not empty
    if len(results_df) > 0:
        column_order = [
            'detail_kode_kelurahan',
            'detail_provinsi',
            'detail_kabupaten_kota',
            'detail_kecamatan',
            'detail_kelurahan_desa',
            'overall_confidence',
            'kecamatan_similarity',
            'kelurahan_similarity',
            'provinsi_similarity',
            'kabupaten_similarity',
            'pos_kelurahan_desa',
            'pos_kecamatan',
            'pos_kabupaten_kota',
            'pos_provinsi',
            'pos_kodepos'
        ]
        
        existing_columns = [col for col in column_order if col in results_df.columns]
        results_df = results_df.select(existing_columns)
    
    # Save to CSV
    output_file = output_dir / f"{province_name}_cascading_matches.csv"
    results_df.write_csv(output_file)
    print(f"\nSaved results to {output_file}")
    
    # Print statistics
    print(f"\n=== Final Statistics ===")
    print(f"Total records saved: {len(results_df)}")
    print(f"Matched records: {len(matched_df)}")
    print(f"Unmatched records: {len(unmatched_df)}")
    
    if len(results_df) > 0:
        avg_conf = results_df['overall_confidence'].mean()
        min_conf = results_df['overall_confidence'].min()
        max_conf = results_df['overall_confidence'].max()
        print(f"Overall confidence: avg={avg_conf:.3f}, min={min_conf:.3f}, max={max_conf:.3f}")


def process_province(province_name: str):
    """Process TRUE cascading matching for a single province."""
    try:
        # Configuration
        province_dir = Path(__file__).parent.parent / "log" / province_name
        output_dir = province_dir
        
        print("=== TRUE Cascading Hierarchical Matcher ===")
        print(f"Processing province: {province_name}")
        print(f"Input directory: {province_dir}")
        print()
        
        # Load data
        detail_df, pos_df = load_join_data(province_dir)
        
        # Perform cascading matching
        print("\n=== Starting Cascading Match ===")
        matches = cascading_match(detail_df, pos_df)
        
        if len(matches) == 0:
            print("WARNING: No matches found after cascading filters.")
        else:
            # Deduplicate 1-to-1
            matches = deduplicate_1to1(matches)
        
        # Get matched detail and POS indices
        matched_detail_indices = {m['detail_idx'] for m in matches}
        matched_pos_indices = {m['pos_idx'] for m in matches}
        
        # Create unmatched detail records
        unmatched_detail = create_unmatched_records(detail_df, matched_detail_indices)
        print(f"\nUnmatched detail records: {len(unmatched_detail)}")
        
        # Create unmatched POS records
        unmatched_pos = create_unmatched_pos_records(pos_df, matched_pos_indices)
        print(f"Unmatched POS records: {len(unmatched_pos)}")
        
        # Save results
        print("\n=== Saving Results ===")
        save_results(matches, unmatched_detail, output_dir, province_name)
        save_unmatched_pos(unmatched_pos, output_dir, province_name)
        
        # Calculate match rate
        total_detail = len(detail_df)
        total_pos = len(pos_df)
        matched_count = len(matched_detail_indices)
        match_rate = (matched_count / total_detail * 100) if total_detail > 0 else 0
        print(f"\nMatch rate: {matched_count}/{total_detail} ({match_rate:.1f}%)")
        print(f"POS utilization: {len(matched_pos_indices)}/{total_pos} ({len(matched_pos_indices)/total_pos*100:.1f}%)")
        
        print("\n=== Matching Complete ===")
        
    except Exception as e:
        print(f"Error processing province {province_name}: {e}")
        raise


def main():
    """Main execution function with argument parsing."""
    parser = argparse.ArgumentParser(
        description='TRUE Cascading Hierarchical Matching Script',
        epilog='Implements strict hierarchical filtering with hard gates at each level.'
    )
    parser.add_argument('--province', type=str, help='Specific province to process')
    args = parser.parse_args()
    
    if args.province:
        process_province(args.province)
    else:
        # Scan all folders in src/log containing both *_detail_join.csv and *_pos_join.csv
        log_dir = Path(__file__).parent.parent / "log"
        provinces = []
        for subdir in log_dir.iterdir():
            if subdir.is_dir():
                detail_csv = subdir / f"{subdir.name}_detail_join.csv"
                pos_csv = subdir / f"{subdir.name}_pos_join.csv"
                if detail_csv.exists() and pos_csv.exists():
                    provinces.append(subdir.name)
        
        print(f"Found {len(provinces)} provinces to process: {', '.join(sorted(provinces))}")
        for province in sorted(provinces):
            try:
                process_province(province)
                print("\n" + "="*60 + "\n")
            except Exception as e:
                print(f"Error processing {province}: {e}")


if __name__ == "__main__":
    main()
