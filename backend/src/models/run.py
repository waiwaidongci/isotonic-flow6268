from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,String,JSON,Text,DateTime,Integer,Boolean
from datetime import datetime,timezone
from src.config.database import Base
class MonotoneRun(Base):
 __tablename__='monotone_runs'
 id:Mapped[int]=mapped_column(primary_key=True)
 study_id:Mapped[int]=mapped_column(ForeignKey('flow_studies.id'))
 name:Mapped[str]=mapped_column(String(180),unique=True)
 config:Mapped[dict]=mapped_column(JSON)
 status:Mapped[str]=mapped_column(String(24),default='queued')
 result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
 error:Mapped[str|None]=mapped_column(Text,nullable=True)
 created_by:Mapped[str]=mapped_column(String(120))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
 # Snapshot of the calibration document in force when the run was queued.
 # Runs queued before calibration tracking existed keep NULL and fit raw values.
 calibration_snapshot:Mapped[dict|None]=mapped_column(JSON,nullable=True)
 calibration_version_id:Mapped[int|None]=mapped_column(ForeignKey('calibration_versions.id'),nullable=True)
 recalibration_seq:Mapped[int]=mapped_column(Integer,default=0,server_default='0')
 is_current:Mapped[bool]=mapped_column(Boolean,default=False,server_default='false')
 diagnostics:Mapped[dict|None]=mapped_column(JSON,nullable=True)
