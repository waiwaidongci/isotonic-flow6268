from datetime import datetime,timezone
from pydantic import BaseModel,Field,ConfigDict,field_validator
class InstrumentInput(BaseModel):
 model_config=ConfigDict(allow_inf_nan=False)
 name:str=Field(min_length=2,max_length=120)
 serial:str=Field(min_length=2,max_length=80)
 description:str=Field(default='',max_length=2000)
def aware_utc(value):
 if value is None:return None
 if value.tzinfo is None:raise ValueError('有效时刻须写明时区，例如 2026-11-01T00:00:00Z')
 return value.astimezone(timezone.utc)
class CalibrationSegmentInput(BaseModel):
 model_config=ConfigDict(allow_inf_nan=False)
 effective_from:datetime
 effective_to:datetime|None=None
 multiplier:float=Field(gt=0,le=1000000)
 offset:float=Field(ge=-1000000,le=1000000)
 note:str=Field(default='',max_length=1000)
 _from=field_validator('effective_from')(aware_utc)
 _to=field_validator('effective_to')(aware_utc)
class CalibrationInput(BaseModel):
 model_config=ConfigDict(allow_inf_nan=False)
 instrument_id:int=Field(gt=0)
 note:str=Field(default='',max_length=2000)
 segments:list[CalibrationSegmentInput]=Field(min_length=1,max_length=50)
