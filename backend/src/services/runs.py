from sqlalchemy import select
from fastapi import HTTPException
from src.models import MonotoneRun
from src.utils.serialize import row
from .studies import source_data
from .validation import validate_source,validate_config,validate_measurement_times
from .audit import record
from .calibration import study_snapshot,validate_instrument_binding

def create_run(db,data,actor):
 study,levels,readings=source_data(db,data.study_id);config=data.model_dump(exclude={'study_id','name'})
 try:validate_source(levels,readings);validate_measurement_times(readings);validate_config(config)
 except ValueError as e:raise HTTPException(422,str(e))
 if db.scalar(select(MonotoneRun).where(MonotoneRun.name==data.name)):raise HTTPException(409,'运行名称已存在')
 snapshot=study_snapshot(db,study)
 if snapshot is not None:
  validate_instrument_binding(db,study['instrument_id'],readings)
 run=MonotoneRun(study_id=data.study_id,name=data.name,config=config,created_by=actor,calibration_snapshot=snapshot,calibration_version_id=snapshot.get('version_id') if snapshot else None,status='queued')
 db.add(run);db.commit()
 try:
  from src.worker import fit_run
  fit_run.delay(run.id)
 except Exception:
  run.status='failed';run.error='队列不可用，请稍后重新创建';db.commit();raise HTTPException(503,run.error)
 record(db,actor,'run.queued',{'run_id':run.id,'calibration_version':snapshot.get('version') if snapshot else None});return row(run)
