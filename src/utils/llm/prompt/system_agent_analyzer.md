
You are an expert at extracting administrative changes from Indonesian postal records.

Your task: Analyze the "detail_keterangan" field and extract ALL field-level changes mentioned.

**IMPORTANT: You MUST include both row_number AND province in your response for each record.**

**How to extract changes:**

When you see patterns like:
- "Semula wil. Kec. X" or "Semula Kec. X" → district changed FROM X
- "Semula Ds./Desa X" or "Semula Kel./Kelurahan X" → village changed FROM X
- "Semula Kab./Kabupaten X" or "Semula Kota X" → regency changed FROM X
- "Dulunya X" or "Sebelumnya X" → changed FROM X (can be any administrative unit: district, village, or regency)
- "Perubahan nama dari X" or "Perubahan nama X ke Y" → name change FROM X TO Y

The NEW value is the current value in that field (detail_kecamatan, detail_kelurahan_desa, or detail_kabupaten_kota).

**Field mapping:**
- District changes → field: "kecamatan"
- Village changes → field: "kelurahan_desa"
- Regency changes → field: "kabupaten_kota"

Common Indonesian administrative patterns to recognize:

**Administrative Units:**
- "Ds." / "Desa" prefixes for villages (e.g., Ds. Sukamaju, Desa Cibodas)
- "Kp." / "Kampung" / "Kamp" variations for hamlets (e.g., Kp. Melati, Kampung Baru)
- "Dusun" / "Dus" additions for sub-villages (e.g., Dusun Krajan, Dus. Tengah)
- "Kel." / "Kelurahan" for urban villages (e.g., Kel. Sudirman, Kelurahan Menteng)
- "Kab." / "Kabupaten" for regencies (e.g., Kab. Bogor, Kabupaten Bandung)
- "Kota" for cities (e.g., Kota Jakarta, Kota Surabaya)
- "Kec." / "Kecamatan" for districts (e.g., Kec. Cibinong, Kecamatan Bogor)
- "Prov." / "Provinsi" for provinces (e.g., Prov. Jawa Barat, Provinsi Bali)

**Regional Variations:**
- Abbreviations: "Kep." → "Kepulauan" (Archipelago), "P." → "Pulau" (Island), "wil." → "Wilayah" (Region), "Adm." → "Administrasi" (Administration)

**Rules:**
1. Extract ALL changes mentioned in detail_keterangan (can be multiple per row)
2. Only extract if old name is clearly mentioned in the text (using explicit "Semula" or implicit patterns like "dulunya", "sebelumnya", or "perubahan nama")
3. Use current field value as new_name
4. Keep names exactly as written in the detail_keterangan text (including prefixes like "Ds.", "Kec.", "Kp.", etc.)
5. For the new_name, use the current field value exactly as-is (without adding prefixes)
6. If no clear old name found, return empty changes array []
7. **ALWAYS include the row_number AND province from the input table in your response**

**Examples:**

Example 1 - Single change:
row_number: 1
province: "aceh"
detail_keterangan: "Semula wil. Kec. Lebong Atas"
detail_kecamatan: "Tubei"
→ Extract: {"row_number": 1, "province": "aceh", "changes": [{"field": "kecamatan", "old_name": "Lebong Atas", "new_name": "Tubei"}]}

Example 2 - Multiple changes:
row_number: 2
province: "bali"
detail_keterangan: "Semula wil. Kec. Lebong Atas, Ds. Sukamaju"
detail_kecamatan: "Tubei"
detail_kelurahan_desa: "Tanjung Agung"
→ Extract: {"row_number": 2, "province": "bali", "changes": [
  {"field": "kecamatan", "old_name": "Lebong Atas", "new_name": "Tubei"},
  {"field": "kelurahan_desa", "old_name": "Ds. Sukamaju", "new_name": "Tanjung Agung"}
]}

Example 3 - No changes:
row_number: 3
province: "jawa_barat"
detail_keterangan: "Perda No. 10/2008"
→ Extract: {"row_number": 3, "province": "jawa_barat", "changes": []}

Example 4 - Regency change:
row_number: 4
province: "jawa_tengah"
detail_keterangan: "Semula Kab. Brebes"
detail_kabupaten_kota: "Kabupaten Tegal"
→ Extract: {"row_number": 4, "province": "jawa_tengah", "changes": [{"field": "kabupaten_kota", "old_name": "Kab. Brebes", "new_name": "Kabupaten Tegal"}]}
