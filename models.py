from sqlalchemy import Column, Integer, String, Boolean, Text
from db import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)
    email = Column(String(160), unique=True, nullable=False, index=True)
    on_leave = Column(Boolean, default=False)
    skills = Column(Text, default="")

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    employee_email = Column(String(160), nullable=False, index=True)
    candidate_name = Column(String(120))
    phone = Column(String(60))
    skills = Column(Text, default="")
    raw_text = Column(Text)     # full OCR’d text
