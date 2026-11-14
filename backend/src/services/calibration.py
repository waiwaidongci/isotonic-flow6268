import hashlib
import json
from datetime import datetime, timezone
from math import isfinite
from sqlalchemy import func, select
from fastapi import HTTPException
from src.models import CalibrationSegment, CalibrationVersion, FlowStudy, Instrument, MonotoneRun, PressureReading
from src.utils.serialize import row
from .audit import record

LEGACY_REASON = '研究未绑定压差仪，沿用原始值分析'

class CalibrationInvalid(ValueError):
 def __init__(self, invalidations, message=None):
  self.invalidations=invalidations
  super().__init__(message or f'校准无法逐片归属：{len(invalidations)} 片读数失效')

def parse_time(value):
 if value is None:return None
 if isinstance(value,datetime):
  return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
 return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)

def iso(value):
 return parse_time(value).isoformat() if value else None

def segment_payload(segment):
 return {'effective_from':iso(segment.effective_from),'effective_to':iso(segment.effective_to),'multiplier':segment.multiplier,'offset':segment.offset,'note':segment.note}

def version_segments(db,version):
 return [segment_payload(s) for s in db.scalars(select(CalibrationSegment).where(CalibrationSegment.calibration_version_id==version.id).order_by(CalibrationSegment.effective_from,CalibrationSegment.id))]

def active_version(db,instrument_id):
 return db.scalar(select(CalibrationVersion).where(CalibrationVersion.instrument_id==instrument_id,CalibrationVersion.status=='active').order_by(CalibrationVersion.version.desc()))

def calibration_fingerprint(instrument_id,segments):
 payload={'instrument_id':instrument_id,'segments':[{'effective_from':iso(s['effective_from']),'effective_to':iso(s['effective_to']),'multiplier':float(s['multiplier']),'offset':float(s['offset'])} for s in segments]}
 return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def instrument_snapshot(db,instrument_id):
 instrument=db.get(Instrument,instrument_id) if instrument_id else None
 if not instrument:return None
 version=active_version(db,instrument_id)
 segments=version_segments(db,version) if version else []
 return {'mode':'calibrated','instrument':{'id':instrument.id,'name':instrument.name,'serial':instrument.serial},'version_id':version.id if version else None,'version':version.version if version else None,'segments':segments,'document_fingerprint':calibration_fingerprint(instrument.id,segments),'available':bool(version)}

def study_snapshot(db,study):
 instrument_id=study.get('instrument_id') if isinstance(study,dict) else getattr(study,'instrument_id',None)
 if not instrument_id:return None
 # A study bound to an instrument that has no active calibration must not
 # silently fall back to raw values; return an unavailable snapshot so
 # matching fails and analysis refuses to publish.
 snapshot=instrument_snapshot(db,instrument_id)
 if snapshot is None:snapshot={'mode':'calibrated','instrument':None,'version_id':None,'version':None,'segments':[],'document_fingerprint':None,'available':False}
 return snapshot

def snapshot_matches(left,right):
 if left is None or right is None:return left is right
 if not right.get('available',True):return False
 return left.get('document_fingerprint')==right.get('document_fingerprint')

def segment_covers(segment,moment):
 start=parse_time(segment['effective_from']);end=parse_time(segment['effective_to'])
 return start<=moment and (end is None or moment<end)

def matching_segments(segments,moment):
 return [s for s in segments if segment_covers(s,moment)]

def calibrate_value(pressure,segment):
 return float(pressure)*float(segment['multiplier'])+float(segment['offset'])

def apply_calibration(readings,snapshot):
 if not snapshot or snapshot.get('mode')=='legacy_raw':
  prepared=[dict(r,corrected_pressure=float(r['pressure']),calibration_basis={'mode':'legacy_raw','reason':LEGACY_REASON}) for r in readings]
  return prepared,[]
 segments=snapshot.get('segments') or []
 if snapshot.get('available',True) is False:
  invalid=[{'reading_id':r.get('id'),'specimen_ref':r.get('specimen_ref'),'level_id':r.get('level_id'),'measured_at':iso(r.get('measured_at')),'raw_pressure':r.get('pressure'),'reason':'calibration_unavailable','detail':'研究绑定的仪器没有生效校准，不能沿用原始值冒充已校正结果'} for r in readings]
  return [dict(r,corrected_pressure=None,calibration_basis=None) for r in readings],invalid
 prepared=[];invalid=[]
 for reading in readings:
  moment=parse_time(reading.get('measured_at'))
  item=dict(reading,corrected_pressure=None,calibration_basis=None)
  if moment is None:
   invalid.append({'reading_id':reading.get('id'),'specimen_ref':reading.get('specimen_ref'),'level_id':reading.get('level_id'),'measured_at':None,'raw_pressure':reading.get('pressure'),'reason':'missing_measured_at','detail':'缺少测量时刻，无法归属校准时段'})
   prepared.append(item);continue
  matches=matching_segments(segments,moment)
  if not matches:
   invalid.append({'reading_id':reading.get('id'),'specimen_ref':reading.get('specimen_ref'),'level_id':reading.get('level_id'),'measured_at':iso(moment),'raw_pressure':reading.get('pressure'),'reason':'not_covered','detail':'测量时刻不在任何生效校准时段内'})
   prepared.append(item);continue
  if len(matches)>1:
   invalid.append({'reading_id':reading.get('id'),'specimen_ref':reading.get('specimen_ref'),'level_id':reading.get('level_id'),'measured_at':iso(moment),'raw_pressure':reading.get('pressure'),'reason':'overlap','detail':f'{len(matches)} 个校准时段在该时刻同时生效，倍率与零点不唯一'})
   prepared.append(item);continue
  segment=matches[0];value=calibrate_value(reading['pressure'],segment)
  if not isfinite(value):
   invalid.append({'reading_id':reading.get('id'),'specimen_ref':reading.get('specimen_ref'),'level_id':reading.get('level_id'),'measured_at':iso(moment),'raw_pressure':reading.get('pressure'),'reason':'corrected_nonfinite','detail':'校准后压差不是有限数'})
   prepared.append(item);continue
  if value<0:
   invalid.append({'reading_id':reading.get('id'),'specimen_ref':reading.get('specimen_ref'),'level_id':reading.get('level_id'),'measured_at':iso(moment),'raw_pressure':reading.get('pressure'),'reason':'corrected_negative','detail':f'校准后压差为负 ({value})'})
   prepared.append(item);continue
  item['corrected_pressure']=value
  item['calibration_basis']={'mode':'calibrated','version_id':snapshot.get('version_id'),'version':snapshot.get('version'),'effective_from':iso(segment['effective_from']),'effective_to':iso(segment['effective_to']),'multiplier':segment['multiplier'],'offset':segment['offset']}
  prepared.append(item)
 return prepared,invalid

def diagnose_segments(segments):
 overlaps=[];gaps=[]
 ordered=sorted(segments,key=lambda s:parse_time(s['effective_from']))
 for left,right in zip(ordered,ordered[1:]):
  if left['effective_to'] is None:
   overlaps.append({'from':iso(right['effective_from']),'to':None,'reason':'上一时段未封口，与后续时段重叠'})
   continue
  left_end=parse_time(left['effective_to']);right_start=parse_time(right['effective_from'])
  if left_end>right_start:overlaps.append({'from':iso(right_start),'to':iso(left_end),'reason':'两个校准时段同时生效'})
  elif left_end<right_start:gaps.append({'from':iso(left_end),'to':iso(right_start),'reason':'时段之间没有生效校准'})
 return overlaps,gaps

def validate_segments(segments):
 if not segments:raise HTTPException(422,'至少需要一个校准时段')
 for index,segment in enumerate(segments):
  start=parse_time(segment['effective_from']);end=parse_time(segment['effective_to'])
  if end is not None and end<=start:raise HTTPException(422,f'第 {index+1} 段结束时刻必须晚于开始时刻')
  if not isfinite(segment['multiplier']) or segment['multiplier']<=0:raise HTTPException(422,f'第 {index+1} 段倍率须为有限正数')
  if not isfinite(segment['offset']):raise HTTPException(422,f'第 {index+1} 段零点须为有限数')

def _comparison(segments,moment):
 matches=matching_segments(segments,moment) if moment else []
 if len(matches)!=1:return None
 return (float(matches[0]['multiplier']),float(matches[0]['offset']))

def build_diagnostics(db,instrument_id,segments,previous_segments):
 overlaps,gaps=diagnose_segments(segments)
 studies=db.scalars(select(FlowStudy).where(FlowStudy.instrument_id==instrument_id).order_by(FlowStudy.id)).all()
 affected_specimens=[];study_reports=[];recompute=[];blocked=[]
 for study in studies:
  readings=db.scalars(select(PressureReading).where(PressureReading.study_id==study.id).order_by(PressureReading.specimen_ref)).all()
  invalid=[];changed=[]
  for reading in readings:
   moment=parse_time(reading.measured_at)
   matches=matching_segments(segments,moment) if moment else []
   if moment is None:
    invalid.append({'reading_id':reading.id,'specimen_ref':reading.specimen_ref,'measured_at':None,'reason':'missing_measured_at','detail':'缺少测量时刻，无法归属校准时段'})
   elif not matches:
    invalid.append({'reading_id':reading.id,'specimen_ref':reading.specimen_ref,'measured_at':iso(moment),'reason':'not_covered','detail':'测量时刻不在任何生效校准时段内','raw_pressure':reading.pressure})
   elif len(matches)>1:
    invalid.append({'reading_id':reading.id,'specimen_ref':reading.specimen_ref,'measured_at':iso(moment),'reason':'overlap','detail':'多个校准时段在该时刻同时生效','raw_pressure':reading.pressure})
   else:
    old=_comparison(previous_segments,moment)
    new=(float(matches[0]['multiplier']),float(matches[0]['offset']))
    if old!=new:
     changed.append({'reading_id':reading.id,'specimen_ref':reading.specimen_ref,'measured_at':iso(moment),'old_multiplier':old[0] if old else None,'old_offset':old[1] if old else None,'new_multiplier':new[0],'new_offset':new[1],'reason':'calibration_changed'})
  for item in invalid:
   affected_specimens.append({'study_id':study.id,'study_name':study.name,**item})
  if invalid:
   status='invalidated';blocked.append(study.id)
  elif changed:
   status='changed';recompute.append(study.id)
  else:
   status='unchanged'
  study_reports.append({'study_id':study.id,'study_name':study.name,'status':status,'affected_count':len(invalid),'changed_count':len(changed),'affected_specimens':[*invalid,*changed]})
 return {'overlaps':overlaps,'gaps':gaps,'affected_specimens':affected_specimens,'studies':study_reports,'recompute_study_ids':recompute,'blocked_study_ids':blocked}

def version_payload(db,version):
 if not version:return None
 return {**row(version),'segments':version_segments(db,version),'diagnostics':version.diagnostics or {}}

def instrument_payload(db,instrument):
 active=active_version(db,instrument.id)
 return {**row(instrument),'active_calibration':version_payload(db,active)}

def create_instrument(db,data,actor):
 if db.scalar(select(Instrument).where(Instrument.name==data.name)):raise HTTPException(409,'仪器名称已存在')
 if db.scalar(select(Instrument).where(Instrument.serial==data.serial)):raise HTTPException(409,'仪器序列号已存在')
 instrument=Instrument(**data.model_dump());db.add(instrument);db.commit();record(db,actor,'instrument.created',{'instrument_id':instrument.id});return instrument_payload(db,instrument)

def create_calibration(db,instrument_id,data,actor,enqueue=True):
 instrument=db.scalar(select(Instrument).where(Instrument.id==instrument_id).with_for_update())
 if not instrument:raise HTTPException(404,'仪器不存在')
 segments=[s.model_dump() for s in data.segments]
 validate_segments(segments)
 previous=active_version(db,instrument_id)
 previous_segments=version_segments(db,previous) if previous else []
 version_number=(db.scalar(select(func.max(CalibrationVersion.version)).where(CalibrationVersion.instrument_id==instrument_id)) or 0)+1
 if previous:previous.status='superseded'
 version=CalibrationVersion(instrument_id=instrument_id,version=version_number,status='active',note=data.note,supersedes_id=previous.id if previous else None,created_by=actor)
 db.add(version);db.flush()
 for segment in segments:
  db.add(CalibrationSegment(calibration_version_id=version.id,effective_from=parse_time(segment['effective_from']),effective_to=parse_time(segment['effective_to']),multiplier=segment['multiplier'],offset=segment['offset'],note=segment['note']))
 db.flush()
 version.diagnostics=build_diagnostics(db,instrument_id,version_segments(db,version),previous_segments)
 db.commit()
 recompute=[]
 if enqueue:
  for study_id in version.diagnostics.get('recompute_study_ids',[]):
   recompute.append(enqueue_recompute(db,db.get(FlowStudy,study_id),actor,f'校准 v{version_number}'))
  reports={report['study_id']:report for report in version.diagnostics.get('studies',[])}
  for study_id in version.diagnostics.get('blocked_study_ids',[]):
   report=reports.get(study_id,{})
   mark_stale(db,db.get(FlowStudy,study_id),instrument_snapshot(db,instrument_id),{'kind':'calibration_invalid','message':'新校准时段无法唯一归属这些滤片，当前结果停用，修复时段后可重试','invalidations':report.get('affected_specimens',[])})
 record(db,actor,'calibration.published',{'instrument_id':instrument_id,'calibration_id':version.id,'version':version_number,'recompute_study_ids':version.diagnostics.get('recompute_study_ids',[]),'blocked_study_ids':version.diagnostics.get('blocked_study_ids',[])})
 return {**version_payload(db,version),'recompute':recompute,'blocked_study_ids':version.diagnostics.get('blocked_study_ids',[])}

def validate_instrument_binding(db,instrument_id,readings):
 instrument=db.get(Instrument,instrument_id)
 if not instrument:raise HTTPException(404,'仪器不存在')
 snapshot=instrument_snapshot(db,instrument_id)
 if not snapshot.get('available'):raise HTTPException(409,'该仪器尚无生效校准，不能绑定研究')
 prepared,invalid=apply_calibration(readings,snapshot)
 if invalid:
  raise HTTPException(422,{'message':'这些滤片的测量时刻无法归属唯一校准时段，未绑定仪器','affected_specimens':invalid,'instrument_id':instrument_id,'calibration':snapshot})
 return snapshot

def bind_study(db,study_id,instrument_id,actor):
 study=db.scalar(select(FlowStudy).where(FlowStudy.id==study_id).with_for_update())
 if not study:raise HTTPException(404,'研究不存在')
 readings=[row(x) for x in db.scalars(select(PressureReading).where(PressureReading.study_id==study_id).order_by(PressureReading.id))]
 if instrument_id is not None:validate_instrument_binding(db,instrument_id,readings)
 old=study.instrument_id;study.instrument_id=instrument_id
 db.commit()
 summary=enqueue_recompute(db,study,actor,'研究绑定仪器变更' if old!=instrument_id else '研究绑定确认')
 record(db,actor,'study.instrument_bound',{'study_id':study_id,'old_instrument_id':old,'instrument_id':instrument_id,'run_id':summary.get('run_id')})
 return {'study':row(study),'recompute':summary}

def mark_stale(db,study,snapshot,diagnostics=None):
 if not study:return []
 stale=[]
 for run in db.scalars(select(MonotoneRun).where(MonotoneRun.study_id==study.id,MonotoneRun.is_current==True)).all():
  if not snapshot_matches(run.calibration_snapshot,snapshot):
   run.is_current=False
   if run.status=='completed':run.status='stale'
   if diagnostics:run.diagnostics={**diagnostics,'calibration_snapshot':snapshot}
   stale.append(run.id)
 db.commit();return stale

def _next_sequence(db,study_id):
 return (db.scalar(select(func.max(MonotoneRun.recalibration_seq)).where(MonotoneRun.study_id==study_id)) or 0)+1

def enqueue_recompute(db,study,actor,reason,config=None,enqueue=True):
 if not study:return {'status':'skipped','error':'研究不存在'}
 template=db.scalar(select(MonotoneRun).where(MonotoneRun.study_id==study.id).order_by(MonotoneRun.id.desc()))
 chosen=config or (template.config if template else None)
 if not chosen:return {'study_id':study.id,'status':'skipped','error':'研究还没有可复用的拟合配置'}
 snapshot=study_snapshot(db,study)
 sequence=_next_sequence(db,study.id)
 stale=mark_stale(db,study,snapshot)
 label='原始值' if snapshot is None else f'校准v{snapshot.get("version")}'
 run=MonotoneRun(study_id=study.id,name=f'{study.name[:90]} · 研究{study.id} · {label} 重算 #{sequence}',config=chosen,created_by=actor,calibration_snapshot=snapshot,calibration_version_id=snapshot.get('version_id') if snapshot else None,recalibration_seq=sequence,status='queued')
 db.add(run);db.commit()
 result={'study_id':study.id,'run_id':run.id,'status':run.status,'reason':reason,'stale_run_ids':stale}
 if enqueue:
  try:
   from src.worker import fit_run
   fit_run.delay(run.id)
  except Exception:
   run.status='failed';run.error='队列不可用，请稍后在运行页重试';db.commit();result['status']='failed';result['error']=run.error
 record(db,actor,'run.recompute_queued',{'study_id':study.id,'run_id':run.id,'reason':reason,'calibration_version':snapshot.get('version') if snapshot else None,'stale_run_ids':stale})
 return dict(result,calibration={'version':snapshot.get('version') if snapshot else None,'version_id':snapshot.get('version_id') if snapshot else None,'mode':('legacy_raw' if snapshot is None else 'calibrated')})

def ensure_recompute(db,study,reason):
 if not study:return None
 snapshot=study_snapshot(db,study)
 for run in db.scalars(select(MonotoneRun).where(MonotoneRun.study_id==study.id,MonotoneRun.status.in_(['queued','running']))).all():
  if snapshot_matches(run.calibration_snapshot,snapshot):return None
 return enqueue_recompute(db,study,'worker',reason)

def commit_result(db,run,result):
 study=db.scalar(select(FlowStudy).where(FlowStudy.id==run.study_id).with_for_update())
 current=study_snapshot(db,study)
 if run.status not in ('queued','running'):
  # A superseded or failed run finishing late must never publish. Only a
  # mismatched calibration needs a fresh recompute; a newer result already
  # covers the current document.
  if not snapshot_matches(run.calibration_snapshot,current):ensure_recompute(db,study,'旧任务晚到')
  return False
 if not snapshot_matches(run.calibration_snapshot,current):
  run.status='superseded';run.error='校准已更新，本任务只代表旧版校准，不能成为整项研究的当前结果';false_result={'kind':'superseded','message':run.error,'calibration_snapshot':run.calibration_snapshot}
  run.diagnostics=false_result;db.commit();ensure_recompute(db,study,'旧版校准任务晚到');return False
 newer=db.scalar(select(MonotoneRun).where(MonotoneRun.study_id==run.study_id,MonotoneRun.is_current==True,MonotoneRun.id>run.id))
 if newer:
  run.status='superseded';run.error='较新的当前结果已经发布，本任务不覆盖';run.diagnostics={'kind':'superseded','message':run.error};db.commit();return False
 for other in db.scalars(select(MonotoneRun).where(MonotoneRun.study_id==run.study_id,MonotoneRun.is_current==True,MonotoneRun.id!=run.id)).all():other.is_current=False
 run.result=result;run.status='completed';run.error=None;run.diagnostics=None;run.is_current=True;db.commit();return True

def fail_run(db,run,kind,message,invalidations=None):
 study=db.get(FlowStudy,run.study_id)
 current=study_snapshot(db,study) if study else None
 if not snapshot_matches(run.calibration_snapshot,current):
  run.status='superseded';run.error='校准已更新，旧任务失败不再作为当前状态';run.diagnostics={'kind':'superseded','message':run.error}
  db.commit();ensure_recompute(db,study,'旧版校准任务失败晚到');return
 run.status='failed';run.error=message[:1000]
 run.diagnostics={'kind':kind,'message':message[:1000],'invalidations':invalidations or [],'calibration_snapshot':run.calibration_snapshot}
 db.commit()

def retry_run(db,run_id,actor):
 original=db.get(MonotoneRun,run_id)
 if not original:raise HTTPException(404,'运行不存在')
 if original.status not in ('failed','superseded','stale'):raise HTTPException(409,'仅失败、已失效或旧版运行可重试')
 study=db.get(FlowStudy,original.study_id)
 if not study:raise HTTPException(404,'研究不存在')
 snapshot=study_snapshot(db,study)
 current=db.scalar(select(MonotoneRun).where(MonotoneRun.study_id==study.id,MonotoneRun.is_current==True,MonotoneRun.status=='completed'))
 if current and snapshot_matches(current.calibration_snapshot,snapshot):
  raise HTTPException(409,f'研究已有同版校准的当前结果 #{current.id}，重试不会覆盖较新结果')
 summary=enqueue_recompute(db,study,actor,f'重试运行 #{run_id}',config=original.config)
 record(db,actor,'run.retried',{'original_run_id':run_id,'new_run_id':summary.get('run_id')})
 return summary

def study_current(db,study_id):
 study=db.get(FlowStudy,study_id)
 if not study:raise HTTPException(404,'研究不存在')
 snapshot=study_snapshot(db,study)
 if snapshot is not None:
  current=db.scalar(select(MonotoneRun).where(MonotoneRun.study_id==study_id,MonotoneRun.is_current==True))
 else:
  current=db.scalar(select(MonotoneRun).where(MonotoneRun.study_id==study_id,MonotoneRun.status=='completed').order_by(MonotoneRun.id.desc()))
 return {'study':row(study),'calibration':snapshot,'current_run':row(current) if current else None,'current_matches_calibration':snapshot_matches(current.calibration_snapshot,snapshot) if current else None}

def trace_study(db,study_id):
 study=db.get(FlowStudy,study_id)
 if not study:raise HTTPException(404,'研究不存在')
 snapshot=study_snapshot(db,study)
 rows=[row(x) for x in db.scalars(select(PressureReading).where(PressureReading.study_id==study_id).order_by(PressureReading.specimen_ref))]
 prepared,invalid=apply_calibration(rows,snapshot)
 invalid_by_id={item['reading_id']:item for item in invalid}
 basis=[];invalid_reasons=[]
 for item in prepared:
  failure=invalid_by_id.get(item['id'])
  entry={'reading_id':item['id'],'specimen_ref':item['specimen_ref'],'level_id':item['level_id'],'measured_at':item.get('measured_at'),'raw_pressure':item['pressure'],'corrected_pressure':item['corrected_pressure'],'basis':item['calibration_basis'],'invalid_reason':failure['reason'] if failure else None,'invalid_detail':failure['detail'] if failure else None}
  basis.append(entry)
  if failure:invalid_reasons.append({'specimen_ref':item['specimen_ref'],'reason':failure['reason'],'detail':failure['detail'],'measured_at':failure.get('measured_at')})
 latest=db.scalar(select(MonotoneRun).where(MonotoneRun.study_id==study_id).order_by(MonotoneRun.id.desc()))
 return {'study':row(study),'calibration':snapshot,'mode':'legacy_raw' if snapshot is None else 'calibrated','basis':basis,'invalid':invalid_reasons,'latest_run':row(latest) if latest else None,'affected_specimens':[{'specimen_ref':x['specimen_ref'],'reason':x['reason'],'detail':x['detail']} for x in invalid_reasons]}
