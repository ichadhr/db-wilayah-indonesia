from pydantic import BaseModel, field_validator
from utils.converter import format_luas, format_number, format_pulau


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


class DistrictCityIndexData(BaseModel):
    no: int
    kode: str
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

    @field_validator("kode", "kabupaten_kota", "keterangan", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v else ""