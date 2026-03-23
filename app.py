import os
import hmac
import hashlib
import json
import time
import jwt
import requests
from urllib.parse import unquote
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from collections import defaultdict
import threading

app = Flask(__name__)

# ✅ CORS مقيّد بـ GitHub Pages فقط
ALLOWED_ORIGINS = [
    "https://rllgn11-gif.github.io",
    "https://web.telegram.org",
    "https://k.tgfiles.com",      # Telegram WebApp CDN
]
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False)

# ============================================================
# 🔑 المفاتيح
# ============================================================
BOT_TOKEN            = os.environ.get("BOT_TOKEN", "")
JWT_SECRET           = os.environ.get("JWT_SECRET", "CHANGE_THIS_SECRET")
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
MINI_APP_URL         = os.environ.get("MINI_APP_URL", "https://rllgn11-gif.github.io/mullak-bot/")
RAILWAY_URL          = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
# ============================================================

bot = telebot.TeleBot(BOT_TOKEN)

# ============================================================
# 🚦 Rate Limiter — حماية من الـ Spam
# ============================================================
_rate_data  = defaultdict(list)   # ip → [timestamps]
_rate_lock  = threading.Lock()

def rate_limit(max_calls: int, period: int):
    """
    max_calls : أقصى عدد طلبات
    period    : خلال كم ثانية
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip  = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
            key = f"{f.__name__}:{ip}"
            now = time.time()
            with _rate_lock:
                calls = [t for t in _rate_data[key] if now - t < period]
                if len(calls) >= max_calls:
                    return jsonify({"error": "طلبات كثيرة جداً — انتظر قليلاً"}), 429
                calls.append(now)
                _rate_data[key] = calls
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ============================================================
# 🛠️ Supabase Helper
# ============================================================
def sb_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def sb_select(table, filters=None, select="*", order=None):
    params = {"select": select}
    if filters:
        params.update(filters)
    if order:
        params["order"] = order
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=params)
    res.raise_for_status()
    return res.json()

def sb_insert(table, data):
    res = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), json=data)
    res.raise_for_status()
    result = res.json()
    return result[0] if isinstance(result, list) else result

def sb_update(table, filters, data):
    res = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=filters, json=data)
    res.raise_for_status()
    result = res.json()
    return result[0] if isinstance(result, list) and result else {"ok": True}

def sb_delete(table, filters):
    res = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=filters)
    res.raise_for_status()
    return {"ok": True}

# ============================================================
# 🔐 تحقق Telegram
# ============================================================
def verify_telegram_init_data(init_data: str):
    try:
        decoded = unquote(init_data)
        parts   = decoded.split("&")
        data_dict = {}
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                data_dict[k] = v
        hash_received = data_dict.pop("hash", None)
        if not hash_received:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()))
        secret_key  = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected    = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, hash_received):
            return None
        return json.loads(data_dict.get("user", "{}"))
    except Exception as e:
        print(f"Telegram verify error: {e}")
        return None

# ============================================================
# 🎫 JWT
# ============================================================
def create_jwt(user_id, first_name):
    return jwt.encode({
        "user_id":    str(user_id),
        "first_name": first_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60 * 60 * 24 * 7
    }, JWT_SECRET, algorithm="HS256")

def verify_jwt_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except:
        return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "غير مصرح"}), 401
        user = verify_jwt_token(auth[7:])
        if not user:
            return jsonify({"error": "انتهت الجلسة — أعد فتح التطبيق"}), 401
        return f(user, *args, **kwargs)
    return decorated

# ============================================================
# 🌐 CORS — مقيّد بالمصادر المسموحة فقط
# ============================================================
@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin", "")
    if any(origin.startswith(o) for o in ALLOWED_ORIGINS):
        response.headers["Access-Control-Allow-Origin"]  = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def options(path):
    return "", 200

# ============================================================
# 🔐 Auth
# ============================================================
@app.route("/auth", methods=["POST"])
@rate_limit(max_calls=10, period=60)   # ✅ 10 محاولات كل دقيقة فقط
def auth():
    data      = request.json or {}
    init_data = data.get("initData", "").strip()

    # ✅ رفض الطلبات الفارغة أو dev_mode بشكل صريح
    if not init_data or init_data == "dev_mode":
        return jsonify({"error": "يجب فتح التطبيق من داخل تيليجرام فقط"}), 403

    user = verify_telegram_init_data(init_data)
    if not user:
        return jsonify({"error": "فشل التحقق من تيليجرام"}), 401

    token = create_jwt(user["id"], user.get("first_name", ""))
    return jsonify({
        "token":      token,
        "user_id":    str(user["id"]),
        "first_name": user.get("first_name", ""),
        "username":   user.get("username", "")
    })

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "app": "مُلّاك 🏠"})

# ============================================================
# 🏗️ العقارات
# ============================================================
@app.route("/api/properties", methods=["GET"])
@require_auth
@rate_limit(max_calls=60, period=60)
def get_properties(user):
    try:
        return jsonify(sb_select("properties", {"user_id": f"eq.{user['user_id']}"}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties", methods=["POST"])
@require_auth
@rate_limit(max_calls=20, period=60)
def add_property(user):
    try:
        d = request.json
        result = sb_insert("properties", {
            "user_id":       str(user["user_id"]),
            "name":          d.get("name", ""),
            "location":      d.get("location", ""),
            "type":          d.get("type", "مالك"),
            "investor_rent": d.get("investor_rent", 0),
            "contract_desc": d.get("contract_desc", "")
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties/<prop_id>", methods=["PUT"])
@require_auth
def edit_property(user, prop_id):
    try:
        d = request.json
        allowed = ["name", "location", "type", "investor_rent", "contract_desc"]
        updates = {k: d[k] for k in allowed if k in d}
        result  = sb_update("properties",
            {"id": f"eq.{prop_id}", "user_id": f"eq.{user['user_id']}"},
            updates)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties/<prop_id>", methods=["DELETE"])
@require_auth
def delete_property(user, prop_id):
    try:
        sb_delete("properties", {"id": f"eq.{prop_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🚪 الوحدات
# ============================================================
@app.route("/api/units", methods=["GET"])
@require_auth
def get_units(user):
    try:
        filters = {"user_id": f"eq.{user['user_id']}"}
        prop_id = request.args.get("property_id")
        if prop_id:
            filters["property_id"] = f"eq.{prop_id}"
        return jsonify(sb_select("units", filters))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/units", methods=["POST"])
@require_auth
def add_unit(user):
    try:
        d = request.json
        result = sb_insert("units", {
            "user_id":     str(user["user_id"]),
            "property_id": d.get("property_id"),
            "unit_num":    d.get("unit_num"),
            "unit_type":   d.get("unit_type", "شقة")
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/units/<unit_id>", methods=["DELETE"])
@require_auth
def delete_unit(user, unit_id):
    try:
        sb_delete("units", {"id": f"eq.{unit_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🧑‍💼 المستأجرون
# ============================================================
@app.route("/api/tenants", methods=["GET"])
@require_auth
def get_tenants(user):
    try:
        return jsonify(sb_select("tenants",
            {"user_id": f"eq.{user['user_id']}"},
            select="*,properties(name,type)"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants", methods=["POST"])
@require_auth
@rate_limit(max_calls=20, period=60)
def add_tenant(user):
    try:
        d = request.json
        row = {
            "user_id":      str(user["user_id"]),
            "name":         d.get("name", ""),
            "phone":        d.get("phone", ""),
            "property_id":  d.get("property_id"),
            "unit_num":     d.get("unit_num"),
            "rent":         d.get("rent", 0),
            "period":       d.get("period", "شهر"),
            "period_count": d.get("period_count", 1),
            "period_label": d.get("period_label", ""),
            "paid":         False
        }
        # إضافة التواريخ إذا توفرت
        if d.get("start_date"):
            row["start_date"] = d["start_date"]
        if d.get("end_date"):
            row["end_date"] = d["end_date"]

        result = sb_insert("tenants", row)
        # تحديث اسم المستأجر في الوحدة
        sb_update("units",
            {"property_id": f"eq.{d['property_id']}",
             "unit_num":    f"eq.{d['unit_num']}",
             "user_id":     f"eq.{user['user_id']}"},
            {"tenant_name": d["name"]})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<tenant_id>", methods=["PUT"])
@require_auth
def edit_tenant(user, tenant_id):
    """تعديل بيانات مستأجر"""
    try:
        d       = request.json
        allowed = ["name", "phone", "rent", "period", "period_count",
                   "period_label", "start_date", "end_date", "paid"]
        updates = {k: d[k] for k in allowed if k in d}
        result  = sb_update("tenants",
            {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
            updates)
        # لو تغير الاسم نحدث الوحدة أيضاً
        if "name" in d:
            tenant_data = sb_select("tenants",
                {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
                select="property_id,unit_num")
            if tenant_data:
                t = tenant_data[0]
                sb_update("units",
                    {"property_id": f"eq.{t['property_id']}",
                     "unit_num":    f"eq.{t['unit_num']}",
                     "user_id":     f"eq.{user['user_id']}"},
                    {"tenant_name": d["name"]})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<tenant_id>", methods=["DELETE"])
@require_auth
def delete_tenant(user, tenant_id):
    """حذف مستأجر وتحرير وحدته"""
    try:
        # جلب بيانات المستأجر أولاً لتحرير الوحدة
        tenants = sb_select("tenants",
            {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
            select="property_id,unit_num")
        if tenants:
            t = tenants[0]
            # تفريغ الوحدة
            sb_update("units",
                {"property_id": f"eq.{t['property_id']}",
                 "unit_num":    f"eq.{t['unit_num']}",
                 "user_id":     f"eq.{user['user_id']}"},
                {"tenant_name": None})
        # حذف المستأجر
        sb_delete("tenants", {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<tenant_id>/pay", methods=["POST"])
@require_auth
def pay_tenant(user, tenant_id):
    try:
        result = sb_update("tenants",
            {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
            {"paid": True})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/reset", methods=["POST"])
@require_auth
def reset_tenants(user):
    try:
        sb_update("tenants", {"user_id": f"eq.{user['user_id']}"}, {"paid": False})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 📤 المصروفات
# ============================================================
@app.route("/api/expenses", methods=["GET"])
@require_auth
def get_expenses(user):
    try:
        return jsonify(sb_select("expenses",
            {"user_id": f"eq.{user['user_id']}"},
            order="created_at.desc"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses", methods=["POST"])
@require_auth
@rate_limit(max_calls=20, period=60)
def add_expense(user):
    try:
        d = request.json
        result = sb_insert("expenses", {
            "user_id":     str(user["user_id"]),
            "category":    d.get("category", "أخرى"),
            "description": d.get("description", ""),
            "amount":      d.get("amount", 0),
            "property_id": d.get("property_id") or None,
            "unit_num":    d.get("unit_num") or None
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses/<exp_id>", methods=["DELETE"])
@require_auth
def delete_expense(user, exp_id):
    try:
        sb_delete("expenses", {"id": f"eq.{exp_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 📊 الإحصائيات
# ============================================================
@app.route("/api/stats", methods=["GET"])
@require_auth
def get_stats(user):
    try:
        uid      = user["user_id"]
        props    = sb_select("properties", {"user_id": f"eq.{uid}"})
        tenants  = sb_select("tenants",    {"user_id": f"eq.{uid}"})
        expenses = sb_select("expenses",   {"user_id": f"eq.{uid}"})
        income   = sum(t["rent"] for t in tenants if t.get("paid"))
        inv_exp  = sum(p.get("investor_rent", 0) for p in props if p.get("type") == "مستثمر")
        man_exp  = sum(e.get("amount", 0) for e in expenses)
        total    = inv_exp + man_exp
        return jsonify({
            "props":    len(props),
            "tenants":  len(tenants),
            "income":   income,
            "expenses": total,
            "net":      income - total
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 📄 تقرير PDF — HTML قابل للطباعة
# ============================================================
@app.route("/api/report/print", methods=["GET"])
@require_auth
def print_report(user):
    """يُرجع HTML احترافي قابل للطباعة كـ PDF"""
    try:
        uid      = user["user_id"]
        fname    = user.get("first_name", "")
        props    = sb_select("properties", {"user_id": f"eq.{uid}"})
        tenants  = sb_select("tenants",    {"user_id": f"eq.{uid}"}, select="*,properties(name)")
        expenses = sb_select("expenses",   {"user_id": f"eq.{uid}"}, order="created_at.desc")

        income   = sum(t["rent"] for t in tenants if t.get("paid"))
        pending  = sum(t["rent"] for t in tenants if not t.get("paid"))
        total_r  = sum(t["rent"] for t in tenants)
        inv_exp  = sum(p.get("investor_rent", 0) for p in props if p.get("type") == "مستثمر")
        man_exp  = sum(e.get("amount", 0) for e in expenses)
        total_e  = inv_exp + man_exp
        net      = income - total_e

        from datetime import date
        today = date.today().strftime("%Y/%m/%d")

        def fmt(n):
            return f"{int(n or 0):,}"

        tenants_rows = ""
        for t in tenants:
            status = "✅ دفع" if t.get("paid") else "❌ لم يدفع"
            color  = "#10b981" if t.get("paid") else "#ef4444"
            prop   = t.get("properties", {}) or {}
            sd     = t.get("start_date", "—")
            ed     = t.get("end_date",   "—")
            tenants_rows += f"""
            <tr>
              <td>{t['name']}</td>
              <td>{t.get('phone','')}</td>
              <td>{prop.get('name','')}</td>
              <td>وحدة {t.get('unit_num','')}</td>
              <td>{t.get('period_label','')}</td>
              <td>{sd}</td>
              <td>{ed}</td>
              <td>{fmt(t.get('rent',0))} ريال</td>
              <td style="color:{color};font-weight:700">{status}</td>
            </tr>"""

        expenses_rows = ""
        for e in expenses:
            prop_name = ""
            if e.get("property_id"):
                p = next((x for x in props if x["id"] == e["property_id"]), None)
                if p:
                    prop_name = p["name"]
            expenses_rows += f"""
            <tr>
              <td>{e.get('category','')}</td>
              <td>{e.get('description','')}</td>
              <td>{prop_name}</td>
              <td>{fmt(e.get('amount',0))} ريال</td>
            </tr>"""

        props_rows = ""
        for p in props:
            pt = [t for t in tenants if t.get("property_id") == p["id"]]
            pi = sum(t["rent"] for t in pt if t.get("paid"))
            pe = sum(e.get("amount",0) for e in expenses if e.get("property_id") == p["id"])
            if p.get("type") == "مستثمر":
                pe += p.get("investor_rent", 0)
            props_rows += f"""
            <tr>
              <td>{p['name']}</td>
              <td>{p.get('location','')}</td>
              <td>{p.get('type','')}</td>
              <td>{len(pt)}</td>
              <td>{fmt(pi)} ريال</td>
              <td>{fmt(pe)} ريال</td>
              <td style="color:{'#f59e0b' if pi-pe>=0 else '#ef4444'};font-weight:700">{fmt(pi-pe)} ريال</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>تقرير مُلّاك — {today}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Segoe UI','Arial',sans-serif; background:#fff; color:#1a1a2e; direction:rtl; font-size:13px; }}
  .header {{ background:linear-gradient(135deg,#1e3a5f,#0a0e1a); color:#fff; padding:28px 32px; display:flex; justify-content:space-between; align-items:center; }}
  .logo {{ font-size:32px; font-weight:900; letter-spacing:-1px; }}
  .logo span {{ color:#10b981; }}
  .header-info {{ text-align:left; font-size:12px; opacity:.8; }}
  .summary {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; padding:20px 32px; background:#f8fafc; border-bottom:2px solid #e2e8f0; }}
  .sum-card {{ background:#fff; border-radius:10px; padding:14px; text-align:center; box-shadow:0 2px 8px rgba(0,0,0,.06); }}
  .sum-num {{ font-size:20px; font-weight:800; margin-bottom:4px; }}
  .sum-label {{ font-size:11px; color:#64748b; }}
  .green {{ color:#10b981; }} .blue {{ color:#3b82f6; }} .red {{ color:#ef4444; }} .gold {{ color:#f59e0b; }} .teal {{ color:#14b8a6; }}
  .section {{ padding:20px 32px; }}
  .section-title {{ font-size:15px; font-weight:800; color:#1e3a5f; margin-bottom:12px; padding-bottom:6px; border-bottom:2px solid #3b82f6; display:flex; align-items:center; gap:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th {{ background:#1e3a5f; color:#fff; padding:10px 8px; text-align:right; font-weight:700; }}
  td {{ padding:9px 8px; border-bottom:1px solid #e2e8f0; }}
  tr:nth-child(even) td {{ background:#f8fafc; }}
  .footer {{ background:#f1f5f9; padding:16px 32px; text-align:center; font-size:11px; color:#64748b; margin-top:20px; }}
  @media print {{
    body {{ font-size:11px; }}
    .summary {{ page-break-inside:avoid; }}
    table {{ page-break-inside:auto; }}
    tr {{ page-break-inside:avoid; }}
    .section {{ page-break-inside:avoid; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="logo">مُلّ<span>اك</span></div>
    <div style="font-size:13px;margin-top:4px;opacity:.7">نظام إدارة العقارات الذكي</div>
  </div>
  <div class="header-info">
    <div style="font-size:14px;font-weight:700;margin-bottom:4px">التقرير المالي الشامل</div>
    <div>المستخدم: {fname}</div>
    <div>التاريخ: {today}</div>
    <div>العقارات: {len(props)} | المستأجرون: {len(tenants)}</div>
  </div>
</div>

<div class="summary">
  <div class="sum-card"><div class="sum-num teal">{fmt(total_r)}</div><div class="sum-label">📥 إجمالي الواردات</div></div>
  <div class="sum-card"><div class="sum-num green">{fmt(income)}</div><div class="sum-label">✅ المحصّل</div></div>
  <div class="sum-card"><div class="sum-num red">{fmt(pending)}</div><div class="sum-label">⏳ المعلّق</div></div>
  <div class="sum-card"><div class="sum-num red">{fmt(total_e)}</div><div class="sum-label">📤 المصروفات</div></div>
  <div class="sum-card"><div class="sum-num {'gold' if net>=0 else 'red'}">{fmt(net)}</div><div class="sum-label">💰 صافي الربح</div></div>
</div>

<div class="section">
  <div class="section-title">🏗️ ملخص العقارات</div>
  <table>
    <tr><th>العقار</th><th>الموقع</th><th>النوع</th><th>المستأجرون</th><th>الدخل المحصّل</th><th>المصروفات</th><th>الصافي</th></tr>
    {props_rows if props_rows else '<tr><td colspan="7" style="text-align:center;color:#64748b">لا يوجد عقارات</td></tr>'}
  </table>
</div>

<div class="section">
  <div class="section-title">🧑‍💼 المستأجرون</div>
  <table>
    <tr><th>الاسم</th><th>الهاتف</th><th>العقار</th><th>الوحدة</th><th>المدة</th><th>البداية</th><th>النهاية</th><th>الإيجار</th><th>الحالة</th></tr>
    {tenants_rows if tenants_rows else '<tr><td colspan="9" style="text-align:center;color:#64748b">لا يوجد مستأجرون</td></tr>'}
  </table>
</div>

<div class="section">
  <div class="section-title">📤 سجل المصروفات</div>
  <table>
    <tr><th>التصنيف</th><th>الوصف</th><th>العقار</th><th>المبلغ</th></tr>
    {expenses_rows if expenses_rows else '<tr><td colspan="4" style="text-align:center;color:#64748b">لا توجد مصروفات</td></tr>'}
    <tr style="background:#fef3c7;font-weight:800">
      <td colspan="3" style="text-align:center">إجمالي المصروفات</td>
      <td style="color:#ef4444">{fmt(total_e)} ريال</td>
    </tr>
  </table>
</div>

<div class="footer">
  تم إنشاء هذا التقرير بواسطة نظام مُلّاك — {today}
</div>

<script>window.onload = function() {{ window.print(); }}</script>
</body>
</html>"""

        return Response(html, mimetype="text/html; charset=utf-8")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🔔 الإشعارات اليومية التلقائية
# ============================================================
def send_daily_reminders():
    """تُرسَل كل يوم الساعة 9 صباحاً بتوقيت السعودية (6 UTC)"""
    if not BOT_TOKEN or not SUPABASE_URL:
        return
    print("🔔 تشغيل التذكيرات اليومية...")
    try:
        # جلب كل المستأجرين غير المدفوعين
        all_tenants = sb_select(
            "tenants",
            {"paid": "eq.false"},
            select="user_id,name,unit_num,rent,period_label,properties(name)"
        )

        if not all_tenants:
            print("✅ لا يوجد مستأجرون متأخرون")
            return

        # تجميع حسب المستخدم
        users_data = {}
        for t in all_tenants:
            uid = t.get("user_id")
            if uid:
                users_data.setdefault(uid, []).append(t)

        # إرسال رسالة لكل مستخدم
        for user_id, unpaid in users_data.items():
            total = sum(t.get("rent", 0) for t in unpaid)
            lines = []
            for t in unpaid[:10]:  # حد أقصى 10 مستأجرين في الرسالة
                prop  = (t.get("properties") or {}).get("name", "")
                label = t.get("period_label", "")
                lines.append(f"• *{t['name']}* — {prop} — وحدة {t.get('unit_num','')} — {int(t.get('rent',0)):,} ريال")

            if len(unpaid) > 10:
                lines.append(f"_... و {len(unpaid)-10} آخرين_")

            msg  = f"🔔 *تذكير يومي — مُلّاك*\n\n"
            msg += f"لديك *{len(unpaid)}* مستأجر لم يدفع:\n\n"
            msg += "\n".join(lines)
            msg += f"\n\n💰 *إجمالي المتأخر: {total:,} ريال*"
            msg += "\n\nافتح التطبيق لتسجيل الدفعات 👇"

            try:
                bot.send_message(
                    int(user_id),
                    msg,
                    parse_mode="Markdown",
                    reply_markup=app_keyboard()
                )
                print(f"✅ أُرسل تذكير لـ {user_id} ({len(unpaid)} مستأجر)")
            except Exception as e:
                print(f"❌ خطأ إرسال لـ {user_id}: {e}")

    except Exception as e:
        print(f"❌ خطأ في التذكيرات اليومية: {e}")


# ============================================================
# 🤖 تيليجرام بوت
# ============================================================
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        update = telebot.types.Update.de_json(request.data.decode("utf-8"))
        bot.process_new_updates([update])
    return "", 200

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    if not RAILWAY_URL:
        return jsonify({"error": "أضف RAILWAY_PUBLIC_DOMAIN في Variables"}), 400
    url = f"https://{RAILWAY_URL}/webhook/{BOT_TOKEN}"
    bot.remove_webhook()
    ok  = bot.set_webhook(url=url, drop_pending_updates=True)
    return jsonify({"ok": ok, "webhook": url})

def app_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        text="🏠 فتح تطبيق مُلّاك",
        web_app=WebAppInfo(url=MINI_APP_URL)
    ))
    return markup

@bot.message_handler(commands=["start"])
def start(msg):
    name = msg.from_user.first_name
    bot.send_message(
        msg.chat.id,
        f"🏠 *أهلاً {name} في مُلّاك!*\n\n"
        f"نظام إدارة عقاراتك الذكي 🤖\n\n"
        f"اضغط الزر أدناه لفتح التطبيق 👇",
        parse_mode="Markdown",
        reply_markup=app_keyboard()
    )

@bot.message_handler(func=lambda m: True)
def default(msg):
    bot.send_message(msg.chat.id, "👋 اضغط الزر لفتح التطبيق", reply_markup=app_keyboard())

# ============================================================
# 🚀 تشغيل
# ============================================================
if __name__ == "__main__":
    # تشغيل جدولة الإشعارات اليومية
    if BOT_TOKEN:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            send_daily_reminders,
            "cron",
            hour=6,       # 9 صباحاً بتوقيت السعودية
            minute=0,
            id="daily_reminders"
        )
        scheduler.start()
        print("✅ جدولة التذكيرات اليومية تعمل (9 ص بتوقيت السعودية)")

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
