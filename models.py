
from sqlalchemy import Column ,Integer ,String,Date,Time,Float,DateTime,ForeignKey,Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Outage(Base):
    __tablename__ = "outages"

    id = Column(Integer,primary_key = True)

    area = Column(String,nullable = False)  
    sub_areas = Column(String,nullable=True)  
    outage_date = Column(Date,nullable=False)
    outage_time = Column(Time,nullable=False)
    latitude = Column(Float,nullable=True)
    longitude = Column(Float,nullable=True)

    def __repr__(self):
        return f"<Outage(area='{self.area}', date='{self.outage_date}')>"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer,primary_key=True)
    name = Column(String,nullable=True)
    email= Column(String,nullable=False,unique=True)
    phone_number = Column(String,nullable=True)
    is_subscribed = Column(Boolean,nullable=True,default=False)
    latitude = Column(Float,nullable=True)
    longitude = Column(Float,nullable=True)

    def __repr__(self):
        return f"<User(email = '{self.email}', lat = '{self.latitude}')"


class Notification(Base):
    __tablename__ = "notifications"

    user_id = Column(Integer,ForeignKey('users.id'),primary_key=True)
    outage_id = Column(Integer,ForeignKey("outages.id"),primary_key=True)
    sent_at = Column(DateTime, default = datetime.utcnow)

    def __repr__(self):
        return F"<Notification(user_id={self.user_id}, outage_id={self.outage_id})>"


# engine = create_engine('sqlite:///outages.db')


# Base.metadata.create_all(engine)

# Session = sessionmaker(bind=engine)