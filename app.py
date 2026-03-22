import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client

app = Flask(__name__)
CORS(app)

# ===== مفاتيح من Railway Variables =====
SUPABASE_URL = os.environ.get("Project", "")
SUPABASE_KEY = os.environ.get("service_role", "")
# ========================================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== مساعد =====
def user_id(req):
    return req.headers.get("X-User-Id", "anonymous")

# ===== العقارات =====
@app.route("/api/properties", methods=["GET"])
def get_properties():
    uid = user_id(request)
    res = supabase.table("properties").select("*").eq("user_id", uid).execute()
    return jsonify(res.data)

@app.route("/api/properties", methods=["POST"])
def add_property():
    uid = user_id(request)
    data = request.json
    data["user_id"] = uid
    res = supabase.table("properties").insert(data).execute()
    return jsonify(res.data[0])

@app.route("/api/properties/<id>", methods=["DELETE"])
def delete_property(id):
    uid = user_id(request)
    supabase.table("properties").delete().eq("id", id).eq("user_id", uid).execute()
    return jsonify({"ok": True})

# ===== الوحدات =====
@app.route("/api/units", methods=["GET"])
def get_units():
    uid = user_id(request)
    prop_id = request.args.get("property_id")
    q = supabase.table("units").select("*").eq("user_id", uid)
    if prop_id:
        q = q.eq("property_id", prop_id)
    res = q.execute()
    return jsonify(res.data)

@app.route("/api/units", methods=["POST"])
def add_unit():
    uid = user_id(request)
    data = request.json
    data["user_id"] = uid
    res = supabase.table("units").insert(data).execute()
    return jsonify(res.data[0])

# ===== المستأجرون =====
@app.route("/api/tenants", methods=["GET"])
def get_tenants():
    uid = user_id(request)
    res = supabase.table("tenants").select("*, properties(name, type)").eq("user_id", uid).execute()
    return jsonify(res.data)

@app.route("/api/tenants", methods=["POST"])
def add_tenant():
    uid = user_id(request)
    data = request.json
    data["user_id"] = uid
    res = supabase.table("tenants").insert(data).execute()
    # تحديث الوحدة كمشغولة
    supabase.table("units").update({"tenant_name": data["name"]}).eq("property_id", data["property_id"]).eq("unit_num", data["unit_num"]).execute()
    return jsonify(res.data[0])

@app.route("/api/tenants/<id>/pay", methods=["POST"])
def pay_tenant(id):
    uid = user_id(request)
    res = supabase.table("tenants").update({"paid": True}).eq("id", id).eq("user_id", uid).execute()
    return jsonify(res.data[0])

@app.route("/api/tenants/reset", methods=["POST"])
def reset_tenants():
    uid = user_id(request)
    supabase.table("tenants").update({"paid": False}).eq("user_id", uid).execute()
    return jsonify({"ok": True})

# ===== المصروفات =====
@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    uid = user_id(request)
    res = supabase.table("expenses").select("*").eq("user_id", uid).order("created_at", desc=True).execute()
    return jsonify(res.data)

@app.route("/api/expenses", methods=["POST"])
def add_expense():
    uid = user_id(request)
    data = request.json
    data["user_id"] = uid
    res = supabase.table("expenses").insert(data).execute()
    return jsonify(res.data[0])

@app.route("/api/expenses/<id>", methods=["DELETE"])
def delete_expense(id):
    uid = user_id(request)
    supabase.table("expenses").delete().eq("id", id).eq("user_id", uid).execute()
    return jsonify({"ok": True})

# ===== الإحصائيات =====
@app.route("/api/stats", methods=["GET"])
def get_stats():
    uid = user_id(request)
    props    = supabase.table("properties").select("*").eq("user_id", uid).execute()
    tenants  = supabase.table("tenants").select("*").eq("user_id", uid).execute()
    expenses = supabase.table("expenses").select("*").eq("user_id", uid).execute()

    paid_income = sum(t["rent"] for t in tenants.data if t["paid"])
    inv_expense = sum(p["investor_rent"] for p in props.data if p["type"] == "مستثمر")
    man_expense = sum(e["amount"] for e in expenses.data)
    total_exp   = inv_expense + man_expense

    return jsonify({
        "props":    len(props.data),
        "tenants":  len(tenants.data),
        "income":   paid_income,
        "expenses": total_exp,
        "net":      paid_income - total_exp
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
