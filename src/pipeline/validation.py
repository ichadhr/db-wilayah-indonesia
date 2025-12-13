from typing import List


def validate_kode_wilayah_data(df) -> List[str]:
    """Validate kode wilayah data for consistency and completeness."""
    errors = []

    if len(df) == 0:
        errors.append("No kode wilayah records found")
        return errors

    # Check required columns
    required_columns = [
        "no",
        "provinsi",
        "kabupaten_kota",
        "nama_kota",
        "singkatan_nama_kota",
        "parent_subdivision",
    ]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")

    # Check for empty/null values in critical fields
    for col in ["provinsi", "kabupaten_kota", "parent_subdivision"]:
        if col in df.columns:
            null_count = df.filter(df[col].is_null() | (df[col] == "")).height
            if null_count > 0:
                errors.append(f"Found {null_count} null/empty values in {col}")

    # Validate parent_subdivision format (should be ID-XX)
    if "parent_subdivision" in df.columns:
        invalid_codes = []
        for row in df.iter_rows(named=True):
            code = str(row.get("parent_subdivision", ""))
            if code and not (code.startswith("ID-") and len(code) >= 4):
                invalid_codes.append(f"{row.get('provinsi', 'Unknown')}: {code}")
        if invalid_codes:
            errors.append(
                f"Invalid parent_subdivision codes: {invalid_codes[:5]}"
            )  # Show first 5

    return errors


def validate_province_data(df) -> List[str]:
    """Validate province index data for consistency and completeness."""
    errors = []

    if len(df) == 0:
        errors.append("No province records found")
        return errors

    # Check required columns
    required_columns = ["provinsi", "kode", "jumlah_kabupaten", "jumlah_kota"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")

    # Check for empty/null values in critical fields
    for col in ["provinsi", "kode"]:
        if col in df.columns:
            null_count = df.filter(df[col].is_null() | (df[col] == "")).height
            if null_count > 0:
                errors.append(f"Found {null_count} null/empty values in {col}")

    # Validate province codes (should be 2 digits)
    if "kode" in df.columns:
        invalid_codes = []
        for row in df.iter_rows(named=True):
            code = str(row.get("kode", ""))
            if code and (len(code) != 2 or not code.isdigit()):
                invalid_codes.append(f"{row.get('provinsi', 'Unknown')}: {code}")
        if invalid_codes:
            errors.append(
                f"Invalid province codes: {invalid_codes[:5]}"
            )  # Show first 5

    # Check for duplicate province names or codes
    if "provinsi" in df.columns:
        names = [
            row["provinsi"] for row in df.iter_rows(named=True) if row.get("provinsi")
        ]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            errors.append(f"Duplicate province names: {list(set(duplicates))}")

    if "kode" in df.columns:
        codes = [
            str(row["kode"]) for row in df.iter_rows(named=True) if row.get("kode")
        ]
        if len(codes) != len(set(codes)):
            duplicates = [code for code in codes if codes.count(code) > 1]
            errors.append(f"Duplicate province codes: {list(set(duplicates))}")

    return errors
