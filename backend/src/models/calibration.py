from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,String,Text,Float,Integer,DateTime,JSON,UniqueConstraint
from datetime import datetime,timezone
from src.config.database import Base
class CalibrationVersion(Base):
 __tablename__='calibration_versions'
 __table_args__=(UniqueConstraint('instrument_id','version'),)
 id:Mapped[int]=mapped_column(primary_key=True)
 instrument_id:Mapped[int]=mapped_column(ForeignKey('instruments.id'))
 version:Mapped[int]=mapped_column(Integer)
 status:Mapped[str]=mapped_column(String(24),default='active')
 note:Mapped[str]=mapped_column(Text,default='')
 diagnostics:Mapped[dict|None]=mapped_column(JSON,nullable=True)
 supersedes_id:Mapped[int|None]=mapped_column(ForeignKey('calibration_versions.id'),nullable=True)
 created_by:Mapped[str]=mapped_column(String(120))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class CalibrationSegment(Base):
 __tablename__='calibration_segments'
 id:Mapped[int]=mapped_column(primary_key=True)
 calibration_version_id:Mapped[int]=mapped_column(ForeignKey('calibration_versions.id'))
 effective_from:Mapped[datetime]=mapped_column(DateTime(timezone=True))
 effective_to:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
 multiplier:Mapped[float]=mapped_column(Float)
 offset:Mapped[float]=mapped_column(Float)
 note:Mapped[str]=mapped_column(Text,default='')
