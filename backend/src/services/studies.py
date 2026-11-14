from sqlalchemy import select
from fastapi import HTTPException
from src.models import FlowStudy,DoseLevel,PressureReading
from src.utils.serialize import row
from .validation import validate_source,validate_measurement_times
from .audit import record
from .calibration import bind_study,enqueue_recompute,iso,validate_instrument_binding

def create_study(db,data,actor):
 if db.scalar(select(FlowStudy).where(FlowStudy.name==data.name)):raise HTTPException(409,'研究名称已存在')
 levels=[{'id':i+1,'label':l.label,'flow':l.flow} for i,l in enumerate(data.levels)];readings=[dict(r.model_dump(),level_id=i+1) for i,l in enumerate(data.levels) for r in l.readings]
 try:validate_source(levels,readings);validate_measurement_times(readings)
 except ValueError as e:raise HTTPException(422,str(e))
 if data.instrument_id is not None:validate_instrument_binding(db,data.instrument_id,readings)
 study=FlowStudy(**data.model_dump(exclude={'levels'}));db.add(study);db.flush()
 for source in data.levels:
  level=DoseLevel(study_id=study.id,label=source.label,flow=source.flow);db.add(level);db.flush()
  for reading in source.readings:db.add(PressureReading(study_id=study.id,level_id=level.id,**reading.model_dump()))
 db.commit();record(db,actor,'study.imported',{'study_id':study.id,'levels':len(levels),'readings':len(readings),'instrument_id':data.instrument_id});return row(study)

def source_data(db,id):
 study=db.get(FlowStudy,id)
 if not study:raise HTTPException(404,'研究不存在')
 return row(study),[row(x) for x in db.scalars(select(DoseLevel).where(DoseLevel.study_id==id).order_by(DoseLevel.id))],[row(x) for x in db.scalars(select(PressureReading).where(PressureReading.study_id==id).order_by(PressureReading.specimen_ref))]

def edit_reading(db,id,data,actor):
 item=db.get(PressureReading,id)
 if not item:raise HTTPException(404,'读数不存在')
 study=db.get(FlowStudy,item.study_id)
 old={'pressure':item.pressure,'measured_at':iso(item.measured_at),'measurement_note':item.measurement_note}
 item.pressure=data.pressure;item.measurement_note=data.measurement_note;item.measured_at=data.measured_at
 db.flush()
 try:
  _,levels,readings=source_data(db,item.study_id);validate_source(levels,readings);validate_measurement_times(readings)
 except ValueError as error:db.rollback();raise HTTPException(422,str(error))
 db.commit();record(db,actor,'reading.revised',{'reading_id':id,'old':old,'new':{'pressure':item.pressure,'measured_at':iso(item.measured_at)}})
 summary=recompute_study(db,study,actor,'原始读数修订') if study and study.instrument_id else None
 return {**row(item),'recompute':summary}

def edit_level(db,id,data,actor):
 level=db.get(DoseLevel,id)
 if not level:raise HTTPException(404,'档位不存在')
 if db.scalar(select(DoseLevel).where(DoseLevel.study_id==level.study_id,DoseLevel.label==data.label,DoseLevel.id!=id)):raise HTTPException(409,'研究内档名重复')
 old=(level.label,level.flow);level.label=data.label;level.flow=data.flow;db.flush()
 try:
  _,levels,readings=source_data(db,level.study_id);validate_source(levels,readings)
 except ValueError as e:db.rollback();raise HTTPException(422,str(e))
 db.commit();record(db,actor,'level.revised',{'level_id':id,'old_label':old[0],'old_flow':old[1]})
 study=db.get(FlowStudy,level.study_id)
 summary=recompute_study(db,study,actor,'档位修订') if study and study.instrument_id else None
 return {**row(level),'recompute':summary}

def recompute_study(db,study,actor,reason):
 if not study:return None
 return enqueue_recompute(db,study,actor,reason)

def bind(db,study_id,instrument_id,actor):
 return bind_study(db,study_id,instrument_id,actor)
