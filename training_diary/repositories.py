"""Data access helpers for training diary operations."""
from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Exercise, TimeOfDay, TrainingSet, User, Workout


def get_or_create_user(session: Session, telegram_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> User:
    user = session.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
    if user:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        return user

    user = User(telegram_id=telegram_id, username=username, first_name=first_name, last_name=last_name)
    session.add(user)
    session.flush()
    return user


def list_exercises(session: Session, user: User) -> List[Exercise]:
    return list(session.execute(select(Exercise).where(Exercise.user_id == user.id).order_by(Exercise.name)).scalars())


def get_or_create_exercise(session: Session, user: User, name: str) -> Exercise:
    exercise = session.execute(
        select(Exercise).where(Exercise.user_id == user.id, func.lower(Exercise.name) == name.lower())
    ).scalar_one_or_none()
    if exercise:
        return exercise
    exercise = Exercise(user_id=user.id, name=name.strip())
    session.add(exercise)
    session.flush()
    return exercise


def get_exercise_by_id(session: Session, user: User, exercise_id: int) -> Optional[Exercise]:
    return session.execute(
        select(Exercise).where(Exercise.user_id == user.id, Exercise.id == exercise_id)
    ).scalar_one_or_none()


def create_workout(session: Session, user: User, exercise: Exercise, performed_on: date, time_of_day: TimeOfDay) -> Workout:
    workout = Workout(user_id=user.id, exercise_id=exercise.id, performed_on=performed_on, time_of_day=time_of_day)
    session.add(workout)
    session.flush()
    return workout


def find_workout(
    session: Session,
    user: User,
    exercise: Exercise,
    performed_on: date,
    time_of_day: TimeOfDay,
) -> Optional[Workout]:
    return (
        session.execute(
            select(Workout)
            .where(
                Workout.user_id == user.id,
                Workout.exercise_id == exercise.id,
                Workout.performed_on == performed_on,
                Workout.time_of_day == time_of_day,
            )
            .order_by(Workout.created_at.desc())
        )
        .scalars()
        .first()
    )


def get_workout(session: Session, workout_id: int, user: User) -> Optional[Workout]:
    return session.execute(select(Workout).where(Workout.id == workout_id, Workout.user_id == user.id)).scalar_one_or_none()


def add_training_set(session: Session, workout: Workout, weight: float, reps: int) -> TrainingSet:
    order = len(workout.sets) + 1
    training_set = TrainingSet(workout_id=workout.id, order=order, weight=weight, reps=reps)
    training_set.update_load()
    session.add(training_set)
    session.flush()
    session.refresh(workout)
    return training_set


def delete_training_set(session: Session, training_set_id: int, user: User) -> bool:
    training_set = (
        session.query(TrainingSet)
        .join(Workout)
        .filter(TrainingSet.id == training_set_id, Workout.user_id == user.id)
        .one_or_none()
    )
    if not training_set:
        return False
    session.delete(training_set)
    session.flush()
    return True


def get_workout_sets(session: Session, workout: Workout) -> Iterable[TrainingSet]:
    session.refresh(workout)
    return workout.sets


def list_workouts(session: Session, user: User, start: Optional[date] = None, end: Optional[date] = None) -> List[Workout]:
    query = select(Workout).where(Workout.user_id == user.id)
    if start:
        query = query.where(Workout.performed_on >= start)
    if end:
        query = query.where(Workout.performed_on <= end)
    query = query.order_by(Workout.performed_on.desc(), Workout.created_at.desc())
    return list(session.execute(query).scalars())


def calculate_loads_by_day(session: Session, user: User, exercise_id: Optional[int] = None):
    query = (
        select(Workout.performed_on, func.sum(TrainingSet.load))
        .join(TrainingSet)
        .where(Workout.user_id == user.id)
        .group_by(Workout.performed_on)
        .order_by(Workout.performed_on)
    )
    if exercise_id:
        query = query.where(Workout.exercise_id == exercise_id)
    return [(row[0], row[1]) for row in session.execute(query).all()]


def calculate_loads_by_exercise(session: Session, user: User):
    query = (
        select(Exercise.name, func.sum(TrainingSet.load))
        .join(Workout, Workout.exercise_id == Exercise.id)
        .join(TrainingSet)
        .where(Exercise.user_id == user.id)
        .group_by(Exercise.name)
        .order_by(Exercise.name)
    )
    return [(row[0], row[1]) for row in session.execute(query).all()]


def remove_workout_if_empty(session: Session, workout: Workout) -> None:
    session.refresh(workout)
    if not workout.sets:
        session.delete(workout)
        session.flush()
