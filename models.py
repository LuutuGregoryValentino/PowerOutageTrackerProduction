from sqlalchemy import Column, Integer, String, Date, Time, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Outage(Base):
    __tablename__ = "outages"

    id = Column(Integer, primary_key=True)
    area = Column(String, nullable=False)  
    sub_areas = Column(String, nullable=True) 
    outage_date = Column(Date, nullable=False)
    outage_time = Column(Time, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # Track when the record was added to the DB
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Helper to convert SQL object to a dictionary for the JS frontend and Email logic"""
        return {
            "id": self.id,
            "area": self.area,
            "sub_areas": self.sub_areas.split(',') if self.sub_areas else [],
            "date": self.outage_date.strftime('%Y-%m-%d'), 
            "time": self.outage_time.strftime('%H:%M'),   
            "latitude": self.latitude,
            "longitude": self.longitude
        }

    def __repr__(self):
        return f"<Outage(area='{self.area}', date='{self.outage_date}')>"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=False, unique=True)
    phone_number = Column(String, nullable=True)
    is_subscribed = Column(Boolean, default=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(email='{self.email}', subscribed={self.is_subscribed})>"

class Notification(Base):
    __tablename__ = "notifications"

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    outage_id = Column(Integer, ForeignKey("outages.id"), primary_key=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification(user_id={self.user_id}, outage_id={self.outage_id})>"