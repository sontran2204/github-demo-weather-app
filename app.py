import os
import sqlite3
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)
load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

DATABASE_PATH = Path(__file__).resolve().parent / "weather.db"
CACHE_TTL_SECONDS = 600  


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE_PATH)
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_cache (
                city_key TEXT PRIMARY KEY,
                city_display TEXT NOT NULL,
                temperature REAL NOT NULL,
                description TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_display TEXT NOT NULL,
                temperature REAL NOT NULL,
                description TEXT NOT NULL,
                searched_at REAL NOT NULL
            )
            """
        )
        db.commit()
    finally:
        db.close()


def save_cache(city_key, city_display, temperature, description):
    now = time.time()
    db = get_db()
    db.execute(
        """
        INSERT INTO weather_cache (city_key, city_display, temperature, description, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(city_key) DO UPDATE SET
            city_display = excluded.city_display,
            temperature = excluded.temperature,
            description = excluded.description,
            updated_at = excluded.updated_at
        """,
        (city_key, city_display, temperature, description, now),
    )
    db.commit()


def save_history(city_display, temperature, description):
    now = time.time()
    db = get_db()
    db.execute(
        """
        INSERT INTO search_history (city_display, temperature, description, searched_at)
        VALUES (?, ?, ?, ?)
        """,
        (city_display, temperature, description, now),
    )
    db.commit()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/weather")
def weather():
    city = (request.args.get("city") or "").strip()
    if not city:
        return jsonify({"error": "City is required"}), 400

    city_key = city.lower()
    now = time.time()
    db = get_db()
    row = db.execute(
        "SELECT city_display, temperature, description, updated_at FROM weather_cache WHERE city_key = ?",
        (city_key,),
    ).fetchone()

    if row is not None and (now - row["updated_at"] < CACHE_TTL_SECONDS):
        save_history(row["city_display"], row["temperature"], row["description"])
        return jsonify(
            {
                "city": row["city_display"],
                "temperature": row["temperature"],
                "description": row["description"],
                "cached": True,
            }
        )

    # Delay uncached requests to make caching behavior easy to verify.
    time.sleep(3)
    response = requests.get(
        "http://api.openweathermap.org/data/2.5/weather",
        params={"q": city, "appid": API_KEY, "units": "metric"},
        timeout=10,
    )
    if response.status_code != 200:
        return jsonify({"error": "City not found or API error"}), 404

    data = response.json()
    temperature = data["main"]["temp"]
    description = data["weather"][0]["description"]
    city_display = data.get("name", city)

    save_cache(city_key, city_display, temperature, description)
    save_history(city_display, temperature, description)

    return jsonify(
        {
            "city": city_display,
            "temperature": temperature,
            "description": description,
            "cached": False,
        }
    )


@app.route("/history")
def history():
    raw = request.args.get("limit", "15")
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = 15
    limit = max(1, min(limit, 50))
    db = get_db()
    rows = db.execute(
        """
        SELECT id, city_display, temperature, description, searched_at
        FROM search_history
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = [
        {
            "id": r["id"],
            "city": r["city_display"],
            "temperature": r["temperature"],
            "description": r["description"],
            "searched_at": r["searched_at"],
        }
        for r in rows
    ]
    return jsonify({"items": items})


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5003)
