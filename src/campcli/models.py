from datetime import date, datetime
from pydantic import BaseModel


class Park(BaseModel):
    park_id: int
    name: str
    region: str | None = None


class Map(BaseModel):
    map_id: int
    park_id: int
    name: str


class AvailableSite(BaseModel):
    park_id: int
    park_name: str
    map_id: int
    map_name: str
    site_id: int
    site_name: str | None = None
    start_date: date
    end_date: date


class Watch(BaseModel):
    id: int | None = None
    park_id: int
    start_date: date
    nights: int
    party_size: int = 1
    label: str | None = None
    created_at: datetime | None = None
