from datetime import datetime,timezone
from pydantic import BaseModel,Field,ConfigDict,field_validator
def aware_utc(value):
 if value is None:return None
 if value.tzinfo is None:raise ValueError('测量时刻须写明时区，例如 2026-11-01T09:00:00Z')
 return value.astimezone(timezone.utc)
class ReadingInput(BaseModel):
 model_config=ConfigDict(allow_inf_nan=False)
 specimen_ref:str=Field(min_length=1,max_length=80)
 pressure:float=Field(ge=0,le=1000000)
 measurement_note:str=Field(default='',max_length=1000)
 measured_at:datetime|None=None
 _measured_at=field_validator('measured_at')(aware_utc)
class ReadingPatch(BaseModel):
 model_config=ConfigDict(allow_inf_nan=False)
 pressure:float=Field(ge=0,le=1000000)
 measurement_note:str=Field(default='',max_length=1000)
 measured_at:datetime|None=None
 _measured_at=field_validator('measured_at')(aware_utc)
