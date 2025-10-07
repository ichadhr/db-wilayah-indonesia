from typing import List, Optional

from pydantic import BaseModel


class PageRange(BaseModel):
    start: Optional[int] = None
    end: Optional[int] = None


class Section(BaseModel):
    type: str
    name: str
    page_range: PageRange
    table_format: str


class ProvinceSections(BaseModel):
    kabupaten_kota_index: Section
    kecamatan_index: Section


class Detail(BaseModel):
    id: str
    name: str
    page_range: PageRange
    table_format: str
    region_type: str


class Province(BaseModel):
    name: str
    total_kabupaten: int
    total_kota: int
    page_range: PageRange
    sections: ProvinceSections
    details: List[Detail]


class AdministrativeStructure(BaseModel):
    name: str
    table_format: str
    page_range: PageRange
    provinces: List[Province]
