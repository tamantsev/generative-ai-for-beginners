"""Flask web application (Telegram mini app) for the training diary."""
from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
from typing import Optional

from flask import Flask, Response, abort, g, jsonify, render_template, request

from .config import get_settings
from .database import get_session_factory, init_db
from .models import TimeOfDay
from .security import verify_telegram_webapp
from .services import TrainingDiaryService, infer_time_of_day


def create_app() -> Flask:
    settings = get_settings()
    init_db()
    app = Flask(__name__, static_folder="static", template_folder="templates")

    @app.before_request
    def authenticate() -> None:
        init_data = request.headers.get("X-Telegram-Init-Data") or request.args.get("initData")
        if not init_data:
            abort(401, description="Missing Telegram authentication data")
        try:
            user_payload = verify_telegram_webapp(init_data)
        except ValueError as exc:  # pragma: no cover - defensive
            abort(403, description=str(exc))

        session = get_session_factory()()
        g.db = session
        g.service = TrainingDiaryService(session)
        g.user = g.service.ensure_user(
            telegram_id=int(user_payload["id"]),
            username=user_payload.get("username"),
            first_name=user_payload.get("first_name"),
            last_name=user_payload.get("last_name"),
        )

    @app.teardown_request
    def close_session(exception: Optional[BaseException]) -> None:  # pragma: no cover - flask handles runtime
        session = getattr(g, "db", None)
        if not session:
            return
        try:
            if exception is None:
                session.commit()
            else:
                session.rollback()
        finally:
            session.close()
            get_session_factory().remove()

    @app.route("/")
    def index() -> str:
        return render_template("index.html", webapp_url=settings.webapp_base_url)

    @app.get("/api/exercises")
    def list_exercises():
        exercises = g.service.list_exercises(g.user)
        return jsonify([{"id": exercise.id, "name": exercise.name} for exercise in exercises])

    @app.post("/api/exercises")
    def create_exercise():
        payload = request.get_json(force=True)
        name = (payload or {}).get("name", "").strip()
        if not name:
            abort(400, description="Exercise name is required")
        exercise = g.service.upsert_exercise(g.user, name)
        return jsonify({"id": exercise.id, "name": exercise.name})

    @app.get("/api/workouts")
    def list_workouts():
        start_param = request.args.get("start")
        end_param = request.args.get("end")
        start_date = datetime.strptime(start_param, "%Y-%m-%d").date() if start_param else None
        end_date = datetime.strptime(end_param, "%Y-%m-%d").date() if end_param else None
        workouts = g.service.list_workouts(g.user, start_date, end_date)
        return jsonify(
            [
                {
                    "id": workout.id,
                    "exercise": workout.exercise.name,
                    "exercise_id": workout.exercise_id,
                    "performed_on": workout.performed_on.isoformat(),
                    "time_of_day": workout.time_of_day.value,
                    "total_load": workout.total_load,
                    "sets": [
                        {
                            "id": training_set.id,
                            "order": training_set.order,
                            "weight": float(training_set.weight),
                            "reps": training_set.reps,
                            "load": training_set.load,
                        }
                        for training_set in workout.sets
                    ],
                }
                for workout in workouts
            ]
        )

    @app.post("/api/workouts")
    def add_set():
        payload = request.get_json(force=True) or {}
        exercise_id = payload.get("exercise_id")
        exercise_name = (payload.get("exercise_name") or "").strip()
        reps = int(payload.get("reps", 0))
        weight = float(payload.get("weight", 0))
        if reps <= 0 or weight <= 0:
            abort(400, description="Reps and weight must be positive numbers")

        performed_on_str = payload.get("performed_on")
        performed_on = datetime.strptime(performed_on_str, "%Y-%m-%d").date() if performed_on_str else date.today()
        time_of_day_value = payload.get("time_of_day")
        if time_of_day_value:
            try:
                time_of_day = TimeOfDay(time_of_day_value)
            except ValueError:
                abort(400, description="Invalid time_of_day value")
        else:
            time_of_day = infer_time_of_day(datetime.now())

        if exercise_id:
            exercise = g.service.get_exercise(g.user, int(exercise_id))
        elif exercise_name:
            exercise = g.service.upsert_exercise(g.user, exercise_name)
        else:
            abort(400, description="Exercise information is required")

        workout = g.service.find_or_create_workout(g.user, exercise, performed_on, time_of_day)
        training_set = g.service.add_training_set(workout, weight, reps)
        return (
            jsonify(
                {
                    "workout_id": workout.id,
                    "set_id": training_set.id,
                    "load": training_set.load,
                }
            ),
            201,
        )

    @app.delete("/api/sets/<int:set_id>")
    def delete_set(set_id: int):
        removed = g.service.delete_training_set(set_id, g.user)
        if not removed:
            abort(404, description="Set not found")
        return ("", 204)

    @app.get("/api/stats/days")
    def loads_by_day():
        exercise_id = request.args.get("exercise_id")
        data = g.service.loads_by_day(g.user, int(exercise_id) if exercise_id else None)
        return jsonify([{"date": day.isoformat(), "load": load} for day, load in data])

    @app.get("/api/stats/exercises")
    def loads_by_exercise():
        data = g.service.loads_by_exercise(g.user)
        return jsonify([{"exercise": name, "load": load} for name, load in data])

    @app.get("/api/export")
    def export_csv():
        start_param = request.args.get("start")
        end_param = request.args.get("end")
        start_date = datetime.strptime(start_param, "%Y-%m-%d").date() if start_param else None
        end_date = datetime.strptime(end_param, "%Y-%m-%d").date() if end_param else None
        workouts = g.service.list_workouts(g.user, start_date, end_date)

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Дата", "Время суток", "Упражнение", "Подход", "Вес", "Повторы", "Нагрузка"])
        for workout in workouts:
            for training_set in workout.sets:
                writer.writerow(
                    [
                        workout.performed_on.isoformat(),
                        workout.time_of_day.value,
                        workout.exercise.name,
                        training_set.order,
                        float(training_set.weight),
                        training_set.reps,
                        training_set.load,
                    ]
                )

        buffer.seek(0)
        filename = f"training-log-{date.today():%Y%m%d}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    return app


app = create_app()
