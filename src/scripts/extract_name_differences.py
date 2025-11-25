#!/usr/bin/env python3
"""
Extract naming differences between detail and pos files from join log CSV.

This script analyzes the parquet_join.csv to find:
1. Kecamatan name differences (same kabupaten, different kecamatan spelling)
2. Kelurahan/Desa name differences (same kabupaten+kecamatan, different kelurahan spelling)

Outputs:
- kecamatan_mapping_candidates.csv: Potential kecamatan name mappings
- kelurahan_mapping_candidates.csv: Potential kelurahan name mappings using fuzzy matching
"""

import polars as pl
from difflib import SequenceMatcher
from collections import defaultdict

def similarity_ratio(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_kecamatan_differences(log_file: str = 'src/log/parquet_join.csv'):
    """Find kecamatan name differences between detail and pos."""
    
    print("="*80)
    print("ANALYZING KECAMATAN NAME DIFFERENCES")
    print("="*80)
    
    # Read the log CSV
    df = pl.read_csv(log_file)
    
    # Separate detail and pos records
    detail_df = df.filter(pl.col('source') == 'detail')
    pos_df = df.filter(pl.col('source') == 'pos')
    
    # Group by kabupaten to find kecamatan differences
    kecamatan_mapping = []
    
    # Get unique kabupaten
    kabupaten_list = df['kabupaten_kota'].unique().to_list()
    
    for kabupaten in kabupaten_list:
        # Get kecamatan from detail and pos for this kabupaten
        detail_kec = detail_df.filter(pl.col('kabupaten_kota') == kabupaten)['kecamatan'].unique().to_list()
        pos_kec = pos_df.filter(pl.col('kabupaten_kota') == kabupaten)['kecamatan'].unique().to_list()
        
        # Find kecamatan in pos that don't exist in detail
        pos_only = set(pos_kec) - set(detail_kec)
        
        if pos_only:
            print(f"\n{kabupaten}:")
            print(f"  Kecamatan in POS but not in DETAIL: {len(pos_only)}")
            
            # Try to find similar names in detail
            for pos_name in pos_only:
                best_match = None
                best_ratio = 0.0
                
                for detail_name in detail_kec:
                    ratio = similarity_ratio(pos_name, detail_name)
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = detail_name
                
                # If similarity > 0.7, it's likely a spelling variation
                if best_match and best_ratio > 0.7:
                    print(f"    {pos_name} -> {best_match} (similarity: {best_ratio:.2f})")
                    kecamatan_mapping.append({
                        'kabupaten_kota': kabupaten,
                        'kecamatan_pos': pos_name,
                        'kecamatan_detail': best_match,
                        'similarity': best_ratio,
                        'status': 'auto_matched'
                    })
                else:
                    print(f"    {pos_name} -> NO MATCH (best: {best_match}, {best_ratio:.2f})")
                    kecamatan_mapping.append({
                        'kabupaten_kota': kabupaten,
                        'kecamatan_pos': pos_name,
                        'kecamatan_detail': best_match or '',
                        'similarity': best_ratio,
                        'status': 'needs_review'
                    })
    
    # Save to CSV
    if kecamatan_mapping:
        df_mapping = pl.DataFrame(kecamatan_mapping)
        output_file = 'src/log/kecamatan_mapping_candidates.csv'
        df_mapping.write_csv(output_file)
        print(f"\n{'='*80}")
        print(f"Saved {len(kecamatan_mapping)} kecamatan mapping candidates to:")
        print(f"  {output_file}")
        print(f"\nAuto-matched (similarity > 0.7): {len([m for m in kecamatan_mapping if m['status'] == 'auto_matched'])}")
        print(f"Needs review: {len([m for m in kecamatan_mapping if m['status'] == 'needs_review'])}")
    
    return kecamatan_mapping

def find_kelurahan_differences(log_file: str = 'src/log/parquet_join.csv'):
    """Find kelurahan/desa name differences using fuzzy matching."""
    
    print("\n" + "="*80)
    print("ANALYZING KELURAHAN/DESA NAME DIFFERENCES")
    print("="*80)
    
    # Read the log CSV
    df = pl.read_csv(log_file)
    
    # Separate detail and pos records
    detail_df = df.filter(pl.col('source') == 'detail')
    pos_df = df.filter(pl.col('source') == 'pos')
    
    kelurahan_mapping = []
    
    # Group by kabupaten + kecamatan
    kabupaten_kecamatan_pairs = df.select(['kabupaten_kota', 'kecamatan']).unique().to_dicts()
    
    print(f"\nAnalyzing {len(kabupaten_kecamatan_pairs)} kabupaten+kecamatan combinations...")
    
    for pair in kabupaten_kecamatan_pairs:
        kabupaten = pair['kabupaten_kota']
        kecamatan = pair['kecamatan']
        
        # Get kelurahan from detail and pos for this kabupaten+kecamatan
        detail_kel = detail_df.filter(
            (pl.col('kabupaten_kota') == kabupaten) & 
            (pl.col('kecamatan') == kecamatan)
        )['kelurahan_desa'].unique().to_list()
        
        pos_kel = pos_df.filter(
            (pl.col('kabupaten_kota') == kabupaten) & 
            (pl.col('kecamatan') == kecamatan)
        )['kelurahan_desa'].unique().to_list()
        
        # Find similar names
        for pos_name in pos_kel:
            best_match = None
            best_ratio = 0.0
            
            for detail_name in detail_kel:
                ratio = similarity_ratio(pos_name, detail_name)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = detail_name
            
            # If similarity > 0.8, it's likely a spelling variation
            if best_match and best_ratio > 0.8 and best_ratio < 1.0:
                kelurahan_mapping.append({
                    'kabupaten_kota': kabupaten,
                    'kecamatan_pos': kecamatan,
                    'kecamatan_detail': kecamatan,
                    'kelurahan_pos': pos_name,
                    'kelurahan_detail': best_match,
                    'similarity': best_ratio,
                    'status': 'auto_matched' if best_ratio > 0.9 else 'needs_review'
                })
    
    # Save to CSV
    if kelurahan_mapping:
        df_mapping = pl.DataFrame(kelurahan_mapping)
        # Sort by similarity descending
        df_mapping = df_mapping.sort('similarity', descending=True)
        output_file = 'src/log/kelurahan_mapping_candidates.csv'
        df_mapping.write_csv(output_file)
        print(f"\nFound {len(kelurahan_mapping)} kelurahan/desa mapping candidates")
        print(f"Saved to: {output_file}")
        print(f"\nTop 10 candidates:")
        for row in df_mapping.head(10).to_dicts():
            print(f"  {row['kelurahan_pos']} -> {row['kelurahan_detail']} ({row['similarity']:.3f})")
        print(f"\nAuto-matched (similarity > 0.9): {len([m for m in kelurahan_mapping if m['status'] == 'auto_matched'])}")
        print(f"Needs review (0.8-0.9): {len([m for m in kelurahan_mapping if m['status'] == 'needs_review'])}")
    
    return kelurahan_mapping

def main():
    """Main entry point."""
    print("\nEXTRACTING NAME DIFFERENCES FROM JOIN LOG")
    print("="*80)
    
    # Find kecamatan differences
    kecamatan_mapping = find_kecamatan_differences()
    
    # Find kelurahan differences
    kelurahan_mapping = find_kelurahan_differences()
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Kecamatan mapping candidates: {len(kecamatan_mapping)}")
    print(f"Kelurahan mapping candidates: {len(kelurahan_mapping)}")
    print(f"\nReview the CSV files in src/log/ to verify mappings.")
    print(f"Then we can apply these mappings to improve the join results.")

if __name__ == "__main__":
    main()
