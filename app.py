import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/FormDB")

def get_conn():
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id   SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    city VARCHAR(255) NOT NULL
                )
            """)

def save_entry(name, city):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO entries (name, city) VALUES (%s, %s)", (name, city))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    city = (data.get("city") or "").strip()
    if name and city:
        save_entry(name, city)
        return jsonify({
            "success": True,
            "message": f"Saved: {name} from {city}",
            "db": "PostgreSQL"
        })
    return jsonify({"success": False, "message": "Please fill in both fields."}), 400

@app.route("/data")
def data():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, city FROM entries ORDER BY id DESC")
            entries = [dict(r) for r in cur.fetchall()]
    return jsonify({"total": len(entries), "entries": entries})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    if debug:
        app.run(debug=True, port=port)
    else:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
