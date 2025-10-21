"""SQLAlchemy models for the training diary."""
from __future__ import annotations

from datetime import datetime, date
from enum import Enum

from sqlalchemy import Column, Date, DateTime, Enum as SqlEnum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from .database import Base


class TimeOfDay(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"

    @classmethod
    def from_hour(cls, hour: int) -> "TimeOfDay":
        if hour < 12:
            return cls.MORNING
        if hour < 17:
            return cls.AFTERNOON
        return cls.EVENING


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    exercises = relationship("Exercise", back_populates="user", cascade="all, delete-orphan")
    workouts = relationship("Workout", back_populates="user", cascade="all, delete-orphan")


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="exercises")
    workouts = relationship("Workout", back_populates="exercise", cascade="all, delete-orphan")


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exercise_id = Column(Integer, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    performed_on = Column(Date, nullable=False, default=date.today)
    time_of_day = Column(SqlEnum(TimeOfDay), nullable=False, default=TimeOfDay.MORNING)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="workouts")
    exercise = relationship("Exercise", back_populates="workouts")
    sets = relationship("TrainingSet", back_populates="workout", cascade="all, delete-orphan", order_by="TrainingSet.order")

    @property
    def total_load(self) -> int:
        return sum(training_set.load for training_set in self.sets)


class TrainingSet(Base):
    __tablename__ = "training_sets"

    id = Column(Integer, primary_key=True)
    workout_id = Column(Integer, ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False, default=1)
    weight = Column(Numeric(10, 2), nullable=False)
    reps = Column(Integer, nullable=False)
    load = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    workout = relationship("Workout", back_populates="sets")

    def update_load(self) -> None:
        self.load = round(self.reps * float(self.weight))
