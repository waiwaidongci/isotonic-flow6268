from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,Text,DateTime
from datetime import datetime,timezone
from src.config.database import Base
class Instrument(Base):
 __tablename__='instruments'
 id:Mapped[int]=mapped_column(primary_key=True)
 name:Mapped[str]=mapped_column(String(120),unique=True)
 serial:Mapped[str]=mapped_column(String(80),unique=True)
 description:Mapped[str]=mapped_column(Text,default='')
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
