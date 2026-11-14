import csv
import io
from fastapi.responses import Response

def _safe(value):
 if isinstance(value,str) and value.startswith(('=','+','-','@')):return "'"+value
 return value

def csv_response(filename,rows,headers):
 output=io.StringIO();writer=csv.writer(output);writer.writerow(headers)
 for values in rows:writer.writerow([_safe(v) for v in values])
 return Response('﻿'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
