from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import get_db
from src.models import Instrument,CalibrationVersion
from src.schemas.instrument import InstrumentInput,CalibrationInput
from src.controllers.dependencies import current_user,writers
from src.services.calibration import create_instrument,create_calibration,instrument_payload,version_payload
router=APIRouter()

@router.get('/instruments')
def instruments(db:Session=Depends(get_db),user=Depends(current_user)):return [instrument_payload(db,x) for x in db.scalars(select(Instrument).order_by(Instrument.id))]

@router.post('/instruments')
def add_instrument(data:InstrumentInput,db:Session=Depends(get_db),user=Depends(writers)):return create_instrument(db,data,user.email)

@router.get('/instruments/{id}/calibrations')
def calibrations(id:int,db:Session=Depends(get_db),user=Depends(current_user)):
 if not db.get(Instrument,id):raise HTTPException(404,'仪器不存在')
 return [version_payload(db,x) for x in db.scalars(select(CalibrationVersion).where(CalibrationVersion.instrument_id==id).order_by(CalibrationVersion.version.desc()))]

@router.post('/instruments/{id}/calibrations')
def publish(id:int,data:CalibrationInput,db:Session=Depends(get_db),user=Depends(writers)):
 if data.instrument_id!=id:raise HTTPException(422,'路径仪器与请求仪器不一致')
 return create_calibration(db,id,data,user.email)

@router.get('/calibrations')
def all(db:Session=Depends(get_db),user=Depends(current_user)):return [version_payload(db,x) for x in db.scalars(select(CalibrationVersion).order_by(CalibrationVersion.id.desc()))]
