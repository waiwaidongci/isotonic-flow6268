import hashlib,json
VERSION='weighted-pava-lodo-calibrated-v2'
def fingerprint(study,levels,readings,config,calibration=None):
 payload={'version':VERSION,'study':study,'levels':sorted(levels,key=lambda x:x['id']),'readings':sorted(readings,key=lambda x:x['specimen_ref']),'config':config,'calibration':({'document_fingerprint':calibration.get('document_fingerprint'),'version':calibration.get('version'),'segments':calibration.get('segments')} if calibration else {'mode':'legacy_raw'})}
 return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
