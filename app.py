import os
import json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_entry(name, city):
    entries = load_data()
    next_id = (entries[-1]["id"] + 1) if entries else 1
    entries.append({"id": next_id, "name": name, "city": city})
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

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
            "storage": "JSON File"
        })
    return jsonify({"success": False, "message": "Please fill in both fields."}), 400

@app.route("/data")
def data():
    entries = load_data()
    return jsonify({"total": len(entries), "entries": list(reversed(entries))})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    if debug:
        app.run(debug=True, port=port)
    else:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
