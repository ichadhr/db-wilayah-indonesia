def format_number(s):
    return str(s).replace('.', '')

def format_luas(s):
    return str(s).replace('.', '').replace(',', '.')

def format_pulau(s):
    return str(s).replace(',', '')

def format_string(s):
    """Format string for CSV output by escaping special characters and handling Unicode."""
    if s is None:
        return ''

    # Convert to string and handle Unicode properly
    original_s = str(s)

    # Check if original string contains special characters that require quoting
    needs_quoting = ',' in original_s or '"' in original_s or '\n' in original_s or '\r' in original_s

    # Replace newlines and tabs with spaces for the final output
    s = original_s.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

    # Remove extra whitespace while preserving single spaces
    s = ' '.join(s.split())

    # If string needs quoting (based on original content), wrap in quotes and escape quotes
    if needs_quoting:
        s = s.replace('"', '""')  # Escape quotes by doubling them
        s = f'"{s}"'  # Wrap in quotes

    return s