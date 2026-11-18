from pydantic import BaseModel, Field

class VolumeInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    series: str = Field(default='日表批次', min_length=2, max_length=160)
    sequence: int | None = Field(default=None, ge=1, le=1000)
    dataset_id: int | None = None
    source: str = Field(default='manual.json', max_length=200)
    records: list[dict] = Field(min_length=1, max_length=5000)

class VolumeAppend(BaseModel):
    records: list[dict] = Field(min_length=1, max_length=5000)

class ExclusionInput(BaseModel):
    day: str = Field(min_length=8, max_length=20)
    zone: str = Field(min_length=1, max_length=60)
    reason: str = Field(min_length=2, max_length=300)

class SealInput(BaseModel):
    params: dict = Field(default_factory=dict)
