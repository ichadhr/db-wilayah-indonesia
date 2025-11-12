from pydantic import BaseModel, field_validator
from utils.converter import format_luas, format_number, format_pulau, format_text, normalize_kabupaten_kota, normalize_ibukota_kabupaten_kota, normalize_kecamatan

class ProvinceIndexData(BaseModel):
    no: int
    kode: str
    provinsi: str
    jumlah_kabupaten: int
    jumlah_kota: int
    jumlah_kecamatan: int
    jumlah_kelurahan: int
    jumlah_desa: int
    luas_wilayah_km2: float
    jumlah_penduduk: int
    jumlah_pulau: int

    @field_validator(
        "no",
        "jumlah_kabupaten",
        "jumlah_kota",
        "jumlah_kecamatan",
        "jumlah_kelurahan",
        "jumlah_desa",
        "jumlah_penduduk",
        mode="before",
    )
    @classmethod
    def validate_int_fields(cls, v):
        if v is None or v == "":
            return 0
        return int(format_number(v))

    @field_validator("jumlah_pulau", mode="before")
    @classmethod
    def validate_pulau_field(cls, v):
        if v is None or v == "":
            return 0
        return int(format_pulau(v))

    @field_validator("luas_wilayah_km2", mode="before")
    @classmethod
    def validate_float_fields(cls, v):
        if v is None or v == "":
            return 0.0
        return float(format_luas(v))

    @field_validator("kode", "provinsi", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v else ""


class RegencyIndexData(BaseModel):
    no: int
    kode_kabupaten_kota: str
    kabupaten_kota: str
    jumlah_kecamatan: int
    jumlah_kelurahan: int
    jumlah_desa: int
    luas_wilayah_km2: float
    jumlah_penduduk: int
    keterangan: str

    @field_validator(
        "no",
        "jumlah_kecamatan",
        "jumlah_kelurahan",
        "jumlah_desa",
        "jumlah_penduduk",
        mode="before",
    )
    @classmethod
    def validate_int_fields(cls, v):
        if v is None or v == "":
            return 0
        return int(format_number(v))

    @field_validator("luas_wilayah_km2", mode="before")
    @classmethod
    def validate_float_fields(cls, v):
        if v is None or v == "":
            return 0.0
        return float(format_luas(v))

    @field_validator("kode_kabupaten_kota", "keterangan", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        """Normalize string fields to clean newlines and extra whitespace."""
        return format_text(v)

    @field_validator("kabupaten_kota", mode="before")
    @classmethod
    def validate_kabupaten_kota_field(cls, v):
        """Normalize kabupaten_kota field by expanding abbreviations."""
        return normalize_kabupaten_kota(v)


class DistrictIndexData(BaseModel):
    no: str
    kode_provinsi: str
    provinsi: str
    ibukota_provinsi: str
    kode_kabupaten_kota: str
    kabupaten_kota: str
    ibukota_kabupaten_kota: str
    kode_kecamatan: str
    kecamatan: str
    jumlah_kabupaten: int
    jumlah_kota: int
    jumlah_kecamatan: int
    jumlah_kelurahan: int
    jumlah_desa: int
    luas_wilayah_km2: float
    jumlah_penduduk: int
    keterangan: str

    # Field validators for data type conversion and validation
    @field_validator("jumlah_kabupaten", "jumlah_kota", "jumlah_kecamatan",
                     "jumlah_kelurahan", "jumlah_desa", "jumlah_penduduk", mode="before")
    @classmethod
    def validate_int_fields(cls, v):
        if v is None or v == "":
            return 0
        return int(format_number(v))

    @field_validator("luas_wilayah_km2", mode="before")
    @classmethod
    def validate_float_fields(cls, v):
        if v is None or v == "":
            return 0.0
        return float(format_luas(v))

    @field_validator("no", "kode_provinsi", "provinsi", "ibukota_provinsi",
                     "kode_kabupaten_kota", "kabupaten_kota", "ibukota_kabupaten_kota",
                     "kode_kecamatan", "kecamatan", "keterangan", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        """Normalize all string fields to clean newlines and extra whitespace."""
        return format_text(v)
    
    @field_validator("kabupaten_kota", mode="before")
    @classmethod
    def validate_kabupaten_kota_field(cls, v):
        """Normalize kabupaten_kota field by expanding abbreviations."""
        return normalize_kabupaten_kota(v)
    
    @field_validator("ibukota_kabupaten_kota", mode="before")
    @classmethod
    def validate_ibukota_kabupaten_kota_field(cls, v):
        """Normalize kabupaten_kota field by expanding abbreviations."""
        return normalize_ibukota_kabupaten_kota(v)
    

class DetailsData(BaseModel):
    kode_provinsi: str
    provinsi: str
    jumlah_kabupaten: int
    jumlah_kota: int
    kode_kabupaten_kota: str
    kabupaten_kota: str
    kode_kecamatan: str
    kecamatan: str
    kode_kelurahan: str
    kelurahan: str
    desa: str
    luas_wilayah_km2: float
    keterangan: str

    # Field validators for data type conversion and validation
    @field_validator("jumlah_kabupaten", "jumlah_kota", mode="before")
    @classmethod
    def validate_int_fields(cls, v):
        if v is None or v == "":
            return 0
        return int(format_number(v))

    @field_validator("luas_wilayah_km2", mode="before")
    @classmethod
    def validate_float_fields(cls, v):
        if v is None or v == "":
            return 0.0
        return float(format_luas(v))

    @field_validator("kode_provinsi", "provinsi",
                     "kode_kabupaten_kota", "kabupaten_kota",
                     "kode_kecamatan", "kecamatan", "kode_kelurahan", "kelurahan", "desa",
                     "keterangan", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        """Normalize all string fields to clean newlines and extra whitespace."""
        return format_text(v)
    
    @field_validator("kabupaten_kota", mode="before")
    @classmethod
    def validate_kabupaten_kota_field(cls, v):
        """Normalize kabupaten_kota field by expanding abbreviations."""
        return normalize_kabupaten_kota(v)
    
    @field_validator("kecamatan", mode="before")
    @classmethod
    def validate_kecamatan_field(cls, v):
        """Normalize kecamatan field by expanding abbreviations."""
        return normalize_kecamatan(v)
    
    # @field_validator("kelurahan", "desa", mode="before")
    # @classmethod
    # def validate_kelurahan_desa_field(cls, v):
    #     """Normalize kelurahan/desa field by expanding abbreviations."""
    #     return normalize_kelurahan_desa(v)