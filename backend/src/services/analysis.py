from math import fsum
from .aggregate import aggregate
from .pava import weighted_pava
from .interpolate import predict
from .inverse import inverse_set
from .lodo import leave_one_dose_out
from .validation import validate_config
from .fingerprint import fingerprint
from .calibration import apply_calibration

def _basis_key(basis):
 return (basis.get('mode',''),basis.get('effective_from') or '',basis.get('effective_to') or '',basis.get('multiplier'),basis.get('offset'))

def _basis_dicts(readings):
 unique={}
 for reading in readings:
  basis=reading['calibration_basis']
  unique[_basis_key(basis)]={'mode':basis.get('mode'),'effective_from':basis.get('effective_from'),'effective_to':basis.get('effective_to'),'multiplier':basis.get('multiplier'),'offset':basis.get('offset'),'reason':basis.get('reason')}
 return [unique[key] for key in sorted(unique)]

def analyze(study,levels,readings,config,calibration=None):
 validate_config(config)
 if study['direction']!='nondecreasing':raise ValueError('研究未预先声明物理非降方向')
 source=[dict(r,pressure=float(r['pressure'])) for r in readings]
 corrected,invalid=apply_calibration(source,calibration)
 if invalid:raise ValueError({'message':f'{len(invalid)} 片读数无法唯一归属校准时段，本项研究不计算；请在曲线页追查失效原因','invalidations':invalid})
 groups=aggregate(levels,corrected)
 fit=weighted_pava([g['mean_pressure'] for g in groups],[g['count'] for g in groups])
 x=[g['flow'] for g in groups]
 knots=[]
 for group,value in zip(groups,fit['fitted']):
  knots.append({'flow':group['flow'],'mean_pressure':group['mean_pressure'],'mean_raw_pressure':group['mean_raw_pressure'],'fitted_pressure':value,'count':group['count'],'labels':group['labels'],'calibration_bases':_basis_dicts(group['readings'])})
 sse=fsum((r['corrected_pressure']-v)**2 for g,v in zip(groups,fit['fitted']) for r in g['readings'])
 legacy_sse=fsum((r['pressure']-v)**2 for g,v in zip(groups,fit['fitted']) for r in g['readings'])
 cv=leave_one_dose_out(groups)
 mode='corrected' if calibration else 'legacy_raw'
 return {'fingerprint':fingerprint(study,levels,readings,config,calibration),'source_study':study,'level_count':len(levels),'unique_flows':len(groups),'reading_count':len(readings),'observed_flow_domain':[x[0],x[-1]],'fitted_pressure_range':[fit['fitted'][0],fit['fitted'][-1]],'knots':knots,'pava_blocks':fit['blocks'],'weighted_between_level_objective':fit['weighted_objective'],'training_raw_mse':sse/len(readings),'training_uncalibrated_mse':legacy_sse/len(readings),'calibration':{'mode':mode,'instrument':(calibration or {}).get('instrument'),'version':(calibration or {}).get('version'),'version_id':(calibration or {}).get('version_id'),'document_fingerprint':(calibration or {}).get('document_fingerprint'),'segments':(calibration or {}).get('segments',[]),'basis_count':len({_basis_key(r['calibration_basis']) for r in corrected}),'explanation':('逐片按测量时刻所在校准时段的倍率与零点校正；原始值原样保留' if mode=='corrected' else '研究未绑定仪器，沿用原分析：只使用原始压差')},'threshold_set':inverse_set(x,fit['fitted'],config['target_pressure']),'predictions':[predict(x,fit['fitted'],q) for q in config['query_flows']],'lodo':cv,'direction':'nondecreasing fixed before observing data','interpolation':'Linear monotone interpolation within observed x domain; outside requests are endpoint-clamped and explicitly marked. No extrapolation promise.','interpretation':'Raw independent specimens define weights. Corrected pressures use the calibration segment in force at each measurement instant; raw values are preserved. LODO refits leave out an entire flow, including duplicate-x named levels. Inverse sets and sensitivity are deterministic fit properties, not confidence intervals, material qualification, or causal guarantees.'}
