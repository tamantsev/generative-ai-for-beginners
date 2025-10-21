"""Shared business logic for training diary components."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from . import repositories
from .models import Exercise, TimeOfDay, TrainingSet, User, Workout


class TrainingDiaryService:
    """High-level operations to manage workouts."""

    def __init__(self, session: Session):
        self.session = session

    def ensure_user(self, telegram_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> User:
        return repositories.get_or_create_user(self.session, telegram_id, username, first_name, last_name)

    def list_exercises(self, user: User):
        return repositories.list_exercises(self.session, user)

    def upsert_exercise(self, user: User, name: str) -> Exercise:
        return repositories.get_or_create_exercise(self.session, user, name)

    def get_exercise(self, user: User, exercise_id: int) -> Optional[Exercise]:
        return repositories.get_exercise_by_id(self.session, user, exercise_id)

    def create_workout(self, user: User, exercise: Exercise, performed_on: date, time_of_day: TimeOfDay) -> Workout:
        return repositories.create_workout(self.session, user, exercise, performed_on, time_of_day)

    def get_workout(self, user: User, workout_id: int) -> Optional[Workout]:
        return repositories.get_workout(self.session, workout_id, user)

    def find_or_create_workout(
        self, user: User, exercise: Exercise, performed_on: date, time_of_day: TimeOfDay
    ) -> Workout:
        existing = repositories.find_workout(self.session, user, exercise, performed_on, time_of_day)
        return existing or self.create_workout(user, exercise, performed_on, time_of_day)

    def add_training_set(self, workout: Workout, weight: float, reps: int) -> TrainingSet:
        return repositories.add_training_set(self.session, workout, weight, reps)

    def delete_training_set(self, training_set_id: int, user: User) -> bool:
        return repositories.delete_training_set(self.session, training_set_id, user)

    def cleanup_workout(self, workout: Workout) -> None:
        repositories.remove_workout_if_empty(self.session, workout)

    def list_workouts(self, user: User, start: Optional[date] = None, end: Optional[date] = None):
        return repositories.list_workouts(self.session, user, start, end)

    def loads_by_day(self, user: User, exercise_id: Optional[int] = None):
        return repositories.calculate_loads_by_day(self.session, user, exercise_id)

    def loads_by_exercise(self, user: User):
        return repositories.calculate_loads_by_exercise(self.session, user)


def infer_time_of_day(moment: datetime) -> TimeOfDay:
    return TimeOfDay.from_hour(moment.hour)
