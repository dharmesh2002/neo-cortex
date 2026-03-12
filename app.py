import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ── Storage ──
# Try file storage first, fall back to memory if filesystem is read-only
_leads = []
_subscribers = []
_use_files = False
_data_dir = None

for path in ["/tmp/solitiq-data", "/app/data", os.path.join(os.path.dirname(__file__), "data")]:
    try:
        os.makedirs(path, exist_ok=True)
        test = os.path.join(path, ".test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        _data_dir = path
        _use_files = True
        print(f"✅ File storage ready: {path}")
        break
    except Exception:
        continue

if not _use_files:
    print("⚠️ No writable directory found. Using in-memory storage.")

LEADS_FILE = os.path.join(_data_dir, "leads.json") if _data_dir else None
SUBSCRIBERS_FILE = os.path.join(_data_dir, "subscribers.json") if _data_dir else None


def load_leads():
    global _leads
    if _use_files and LEADS_FILE:
        try:
            if os.path.exists(LEADS_FILE):
                with open(LEADS_FILE, "r", encoding="utf-8") as f:
                    _leads = json.load(f)
        except Exception:
            _leads = []
    return _leads


def save_leads():
    if _use_files and LEADS_FILE:
        try:
            with open(LEADS_FILE, "w", encoding="utf-8") as f:
                json.dump(_leads, f, indent=2)
        except Exception:
            pass


def load_subscribers():
    global _subscribers
    if _use_files and SUBSCRIBERS_FILE:
        try:
            if os.path.exists(SUBSCRIBERS_FILE):
                with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                    _subscribers = json.load(f)
        except Exception:
            _subscribers = []
    return _subscribers


def save_subscribers():
    if _use_files and SUBSCRIBERS_FILE:
        try:
            with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
                json.dump(_subscribers, f, indent=2)
        except Exception:
            pass


# Load existing data on startup
load_leads()
load_subscribers()


# ── Routes ──

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/lead", methods=["POST"])
def create_lead():
    try:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        if not name or not email:
            return jsonify({"success": False, "message": "Name and email are required."}), 400

        next_id = (_leads[-1]["id"] + 1) if _leads else 1
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
        _leads.append(lead)
        save_leads()
        return jsonify({"success": True, "message": "Thank you! We'll be in touch soon.", "id": next_id})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


@app.route("/api/leads", methods=["GET"])
def get_leads():
    try:
        return jsonify({"total": len(_leads), "leads": list(reversed(_leads))})
    except Exception as e:
        return jsonify({"total": 0, "leads": [], "error": str(e)})


@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip()
        if not email:
            return jsonify({"success": False, "message": "Email is required."}), 400

        if any(s["email"] == email for s in _subscribers):
            return jsonify({"success": True, "message": "You're already subscribed!"})

        next_id = (_subscribers[-1]["id"] + 1) if _subscribers else 1
        _subscribers.append({
            "id": next_id,
            "email": email,
            "subscribed_at": datetime.utcnow().isoformat() + "Z",
        })
        save_subscribers()
        return jsonify({"success": True, "message": "Successfully subscribed!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "storage": "file" if _use_files else "memory",
        "data_dir": _data_dir,
        "leads_count": len(_leads),
        "subscribers_count": len(_subscribers),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    if debug:
        app.run(debug=True, port=port)
    else:
        from waitress import serve
        print(f"🚀 Solitiq running on port {port}")
        serve(app, host="0.0.0.0", port=port)
