import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
LEADS_FILE = os.path.join(BASE_DIR, "leads.json")
SUBSCRIBERS_FILE = os.path.join(BASE_DIR, "subscribers.json")


def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/lead", methods=["POST"])
def create_lead():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not email:
        return jsonify({"success": False, "message": "Name and email are required."}), 400

    leads = load_json(LEADS_FILE)
    next_id = (leads[-1]["id"] + 1) if leads else 1
    lead = {
        "id": next_id,
        "name": name,
        "email": email,
        "phone": (data.get("phone") or "").strip(),
        "company": (data.get("company") or "").strip(),
        "service": (data.get("service") or "").strip(),
        "message": (data.get("message") or "").strip(),
        "status": "new",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    leads.append(lead)
    save_json(LEADS_FILE, leads)
    return jsonify({"success": True, "message": "Thank you! We'll be in touch soon.", "id": next_id})


@app.route("/api/leads", methods=["GET"])
def get_leads():
    leads = load_json(LEADS_FILE)
    return jsonify({"total": len(leads), "leads": list(reversed(leads))})


@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400

    subscribers = load_json(SUBSCRIBERS_FILE)
    if any(s["email"] == email for s in subscribers):
        return jsonify({"success": True, "message": "You're already subscribed!"})

    next_id = (subscribers[-1]["id"] + 1) if subscribers else 1
    subscribers.append({
        "id": next_id,
        "email": email,
        "subscribed_at": datetime.utcnow().isoformat() + "Z",
    })
    save_json(SUBSCRIBERS_FILE, subscribers)
    return jsonify({"success": True, "message": "Successfully subscribed!"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    if debug:
        app.run(debug=True, port=port)
    else:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
