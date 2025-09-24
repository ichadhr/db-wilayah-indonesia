from typing import List

from pydantic import BaseModel


# Define the Pydantic model
class KodeWilayah(BaseModel):
    no: int
    provinsi: str
    kabupaten_kota: str
    nama_kota: str
    singkatan_nama_kota: str
    parent_subdivision: str


class TableKodeWilayah(BaseModel):
    records: List[KodeWilayah]
