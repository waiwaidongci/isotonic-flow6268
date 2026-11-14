import json
from pathlib import Path
from celery import Celery
from src.config.database import SessionLocal
from src.config.settings import REDIS_URL,ARTIFACT_DIR
from src.models import MonotoneRun
from src.services.studies import source_data
from src.services.analysis import analyze
from src.services.audit import record
from src.services.calibration import commit_result,fail_run
app=Celery('isotonic_flow',broker=REDIS_URL,backend=REDIS_URL)
app.conf.update(task_track_started=True,worker_prefetch_multiplier=1,task_acks_late=True)
@app.task(name='flow.fit',soft_time_limit=120,time_limit=150)
def fit_run(id):
 with SessionLocal() as db:
  run=db.get(MonotoneRun,id)
  if not run or run.status in ('completed','superseded'):return
  run.status='running';db.commit()
  try:
   study,levels,readings=source_data(db,run.study_id);result=analyze(study,levels,readings,run.config,run.calibration_snapshot)
   Path(ARTIFACT_DIR).mkdir(parents=True,exist_ok=True);Path(ARTIFACT_DIR,f'flow-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
   published=commit_result(db,run,result)
   record(db,'worker','run.completed' if published else 'run.superseded',{'run_id':id,'lodo_mse':result['lodo']['mse'],'calibration_version':result['calibration'].get('version'),'current':published})
  except Exception as error:
   db.rollback()
   invalid=getattr(error,'args',[None])[0] if error.args else None
   if isinstance(invalid,dict) and 'invalidations' in invalid:fail_run(db,run,'calibration_invalid',invalid.get('message',str(error)),invalid.get('invalidations'))
   else:fail_run(db,run,'analysis_error',str(error))
   record(db,'worker','run.failed',{'run_id':id,'error':str(error)[:500]})
