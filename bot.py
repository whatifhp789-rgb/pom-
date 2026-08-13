"""
Telegram Payment Bot — Dynamic UPI QR Generator
- QR scan karne par automatically plan amount set ho jati hai
- Multi-owner support
- No manual amount entry needed
"""

import os
import json
import sqlite3
import sys
import time
import random
import urllib.parse
import requests

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")
API = "https://api.telegram.org"

# ==================== MULTI-OWNER CONFIG ====================
BOT_TOKEN = "8708150884:AAHA7Wn3dddxzyc1cEzKRpA3pXtj-DWv3EY"
OWNER_IDS = [7130712170, 8754004223]

DEFAULTS = {
    "bot_token": BOT_TOKEN,
    "admin_chat_id": str(OWNER_IDS[0]),
    "upi_id": "your-upi@paytm",  # 🔥 Yahan apna UPI ID daalo
    "welcome_text": "Welcome! Choose a plan below.",
    "access_link": "https://your-access-link.com",
    "submitted_text": "✅ Request Submitted!\n\n🆔 Order #{order}\n⏳ Your plan will be activated after verification.",
    "approved_text": "✅ Payment Approved!\n\n🆔 Order #{order} — Plan: {plan}\nHere is your access link:",
    "declined_text": "❌ Payment Not Verified\n\n🆔 Order #{order} — Plan: {plan}\nPlease contact support.",
}

MEDIA_LIMIT = 10

# ==================== DB FUNCTIONS ====================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("""CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            price REAL NOT NULL,
            reply_text TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT NOT NULL DEFAULT '',
            chat_id TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            full_name TEXT NOT NULL DEFAULT '',
            plan_label TEXT NOT NULL DEFAULT '',
            price REAL NOT NULL DEFAULT 0,
            photo_file_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'selected',
            created_at REAL NOT NULL DEFAULT 0)""")
        c.execute("CREATE TABLE IF NOT EXISTS state (chat_id TEXT PRIMARY KEY, step TEXT NOT NULL)")
        
        for k, v in DEFAULTS.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
        if not c.execute("SELECT COUNT(*) AS n FROM plans").fetchone()["n"]:
            c.executemany(
                "INSERT INTO plans (label, price, reply_text, position) VALUES (?, ?, ?, ?)",
                [
                    ("Basic Plan", 49, "Pay ₹49 on the QR above and send the payment screenshot here.", 1),
                    ("Premium Plan", 99, "Pay ₹99 on the QR above and send the payment screenshot here.", 2),
                ],
            )

def get(key):
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULTS.get(key, "")

def put(key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

def plans(active_only=True):
    q = "SELECT * FROM plans" + (" WHERE active = 1" if active_only else "") + " ORDER BY position, id"
    with db() as c:
        return [dict(r) for r in c.execute(q).fetchall()]

def get_payment_by_order(order_code):
    with db() as c:
        return c.execute("SELECT * FROM payments WHERE order_code = ?", (order_code,)).fetchone()

def update_payment_status(order_code, status):
    with db() as c:
        c.execute("UPDATE payments SET status = ? WHERE order_code = ?", (status, order_code))

def all_chat_ids():
    with db() as c:
        return [r["chat_id"] for r in c.execute("SELECT DISTINCT chat_id FROM payments").fetchall()]

# ==================== 🔥 DYNAMIC UPI QR GENERATOR ====================
def generate_upi_qr(upi_id, amount, order_id, name="Store"):
    """
    Generate UPI QR code with dynamic amount
    Scan karne par automatically amount set ho jati hai
    """
    # UPI deep link with amount
    upi_link = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR&tn=Order_{order_id}"
    
    # Encode for QR
    encoded = urllib.parse.quote(upi_link, safe='')
    
    # QR API (free)
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={encoded}"
    
    try:
        response = requests.get(qr_url, timeout=30)
        qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"qr_{order_id}.png")
        with open(qr_path, 'wb') as f:
            f.write(response.content)
        return qr_path
    except Exception as e:
        print(f"QR generation error: {e}")
        return None

def new_order_code():
    with db() as c:
        for _ in range(50):
            code = str(random.randint(1000, 9999))
            if not c.execute("SELECT 1 FROM payments WHERE order_code = ?", (code,)).fetchone():
                return code
    return str(random.randint(1000, 9999))

# ==================== TELEGRAM FUNCTIONS ====================
def call(method, **payload):
    token = get("bot_token")
    res = requests.post(f"{API}/bot{token}/{method}", json=payload, timeout=90)
    data = res.json()
    if not data.get("ok"):
        print(f"[telegram] {method} failed: {data.get('description')}")
    return data

def send(chat_id, text, keyboard=None):
    args = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        args["reply_markup"] = keyboard
    return call("sendMessage", **args)

def send_photo(chat_id, file_path, caption="", keyboard=None):
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            args = {"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"}
            if keyboard:
                args["reply_markup"] = keyboard
            return requests.post(f"{API}/bot{get('bot_token')}/sendPhoto", data=args, files={"photo": f}).json()
    return None

def send_media(chat_id, items, caption=""):
    if not items:
        return None
    if len(items) == 1:
        it = items[0]
        method = "sendPhoto" if it["kind"] == "photo" else "sendVideo"
        args = {"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"}
        args["photo" if it["kind"] == "photo" else "video"] = it["file_id"]
        return call(method, **args)
    group = []
    for i, it in enumerate(items):
        entry = {"type": it["kind"], "media": it["file_id"]}
        if i == 0 and caption:
            entry["caption"] = caption[:1024]
            entry["parse_mode"] = "HTML"
        group.append(entry)
    return call("sendMediaGroup", chat_id=chat_id, media=group)

def render(template, order="", plan=""):
    return (template or "").replace("{order}", str(order)).replace("{plan}", str(plan))

def notify(chat_id, text_key, order="", plan="", extra=""):
    body = render(get(text_key), order, plan) + (("\n" + extra) if extra else "")
    return send(chat_id, body)

def start_keyboard():
    rows = [[{"text": f"{p['label']} — ₹{int(p['price'])}", "callback_data": f"plan:{p['id']}"}] for p in plans()]
    return {"inline_keyboard": rows}

def pay_keyboard(pid):
    return {
        "inline_keyboard": [
            [{"text": "✅ I have paid", "callback_data": f"paid:{pid}"}],
            [{"text": "❌ Cancel", "callback_data": "cancel"}],
        ]
    }

def review_keyboard(payment_id):
    return {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"pay_ok:{payment_id}"},
            {"text": "❌ Decline", "callback_data": f"pay_no:{payment_id}"},
        ]]
    }

def dashboard_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📊 Dashboard", "callback_data": "dash"},
             {"text": "💰 Plans", "callback_data": "plans:list"}],
            [{"text": "📝 Pending Payments", "callback_data": "pay:list"},
             {"text": "⚙️ Settings", "callback_data": "settings"}],
            [{"text": "📢 Broadcast", "callback_data": "bcast"}],
        ]
    }

def is_admin(chat_id):
    return int(chat_id) in OWNER_IDS

# ==================== HANDLERS ====================
def handle_message(msg):
    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return
    frm = msg.get("from", {}) or {}
    text = (msg.get("text") or msg.get("caption") or "").strip()
    
    # Payment screenshot
    if msg.get("photo") and not is_admin(chat_id):
        file_id = msg["photo"][-1]["file_id"]
        with db() as c:
            sel = c.execute("SELECT * FROM payments WHERE chat_id = ? AND status = 'selected' ORDER BY id DESC LIMIT 1", (str(chat_id),)).fetchone()
            if sel:
                c.execute("UPDATE payments SET photo_file_id = ?, status = 'pending' WHERE id = ?", (file_id, sel["id"]))
                order_code = sel["order_code"]
                label = sel["plan_label"]
                price = sel["price"]
            else:
                return send(chat_id, "❌ No pending payment found. Please select a plan first with /start")
        
        notify(chat_id, "submitted_text", order_code, label)
        who = "@" + frm.get("username", "") if frm.get("username") else frm.get("first_name", str(chat_id))
        
        for admin_id in OWNER_IDS:
            try:
                send_photo(admin_id, None, file_id=file_id,
                           caption=f"🧾 <b>Payment for review</b>\n🆔 #{order_code}\n{label} — ₹{int(price)}\nFrom: {who} (<code>{chat_id}</code>)",
                           keyboard=review_keyboard(sel["id"]))
            except:
                pass
        return

    # UTR / Transaction ID
    if text and not text.startswith("/") and not is_admin(chat_id):
        with db() as c:
            sel = c.execute("SELECT * FROM payments WHERE chat_id = ? AND status = 'selected' ORDER BY id DESC LIMIT 1", (str(chat_id),)).fetchone()
            if sel:
                c.execute("UPDATE payments SET status = 'pending' WHERE id = ?", (sel["id"],))
                notify(chat_id, "submitted_text", sel["order_code"], sel["plan_label"])
                for admin_id in OWNER_IDS:
                    try:
                        send(admin_id, f"🧾 <b>Payment for review (UTR)</b>\n🆔 #{sel['order_code']}\n{sel['plan_label']} — ₹{int(sel['price'])}\nUTR: <code>{text}</code>\nFrom: {who} (<code>{chat_id}</code>)",
                            review_keyboard(sel["id"]))
                    except:
                        pass
                return

    # Commands
    if text.startswith("/start"):
        items = []  # welcome_media()
        if items:
            send_media(chat_id, items, get("welcome_text"))
        else:
            send(chat_id, get("welcome_text"))
        return send(chat_id, "Choose a plan 👇", start_keyboard())

    if text.startswith("/admin") or text.startswith("/dashboard"):
        if is_admin(chat_id):
            return send(chat_id, "👑 Admin Panel", dashboard_keyboard())
        return send(chat_id, "❌ Not authorized")

    send(chat_id, "Send /start to see available plans.")

def handle_callback(cq):
    cq_id = cq["id"]
    data = cq.get("data") or ""
    frm = cq.get("from", {}) or {}
    chat_id = cq.get("message", {}).get("chat", {}).get("id")

    def answer(text=""):
        call("answerCallbackQuery", callback_query_id=cq_id, text=text)

    # ==================== 🔥 PLAN SELECT — DYNAMIC QR ====================
    if data.startswith("plan:"):
        answer()
        pid = data.split(":")[1]
        with db() as c:
            p = c.execute("SELECT * FROM plans WHERE id = ?", (pid,)).fetchone()
        if not p:
            return
        
        order_code = new_order_code()
        with db() as c:
            c.execute("DELETE FROM payments WHERE chat_id = ? AND status = 'selected'", (str(chat_id),))
            c.execute("INSERT INTO payments (order_code, chat_id, username, full_name, plan_label, price, status, created_at) VALUES (?,?,?,?,?,?,'selected',?)",
                      (order_code, str(chat_id), frm.get("username", ""), frm.get("first_name", ""),
                       p["label"], p["price"], time.time()))
        
        upi_id = get("upi_id") or "your-upi@paytm"
        qr_path = generate_upi_qr(upi_id, p["price"], order_code)
        
        caption = f"✅ <b>{p['label']}</b> — ₹{int(p['price'])}\n\n"
        caption += f"🆔 Order #{order_code}\n"
        caption += f"💳 UPI: <code>{upi_id}</code>\n\n"
        caption += f"🔹 QR scan karne par automatically ₹{int(p['price'])} set ho jayega\n"
        caption += f"🔹 You don't need to enter amount manually\n\n"
        caption += f"After payment, tap 'I have paid' and send screenshot."
        
        if qr_path and os.path.exists(qr_path):
            send_photo(chat_id, qr_path, caption, pay_keyboard(pid))
            try:
                os.remove(qr_path)
            except:
                pass
        else:
            send(chat_id, "❌ QR generation failed. Please contact support.")
        return

    if data.startswith("paid:"):
        answer("Send screenshot or UTR")
        return send(chat_id, "✅ Great!\n\n📸 Send your payment screenshot, or\n📝 Type your UTR / Transaction ID")

    if data == "cancel":
        answer("Cancelled")
        with db() as c:
            c.execute("DELETE FROM payments WHERE chat_id = ? AND status = 'selected'", (str(chat_id),))
        return send(chat_id, "Cancelled. Use /start to choose a plan.")

    # ==================== ADMIN ONLY ====================
    if not is_admin(frm.get("id")):
        return answer("Only admin can do this.")

    if data == "dash":
        answer()
        with db() as c:
            payments = c.execute("SELECT * FROM payments").fetchall()
            pending = [p for p in payments if p["status"] == "pending"]
            approved = [p for p in payments if p["status"] == "approved"]
            declined = [p for p in payments if p["status"] == "declined"]
            total_revenue = sum(p["price"] for p in approved)
        
        text = f"📊 <b>Dashboard</b>\n━━━━━━━━━━━━━━━━━\n"
        text += f"👥 Customers: {len(set(p['chat_id'] for p in payments))}\n"
        text += f"🧾 Pending: {len(pending)}\n"
        text += f"✅ Approved: {len(approved)}\n"
        text += f"❌ Declined: {len(declined)}\n"
        text += f"💰 Revenue: ₹{int(total_revenue)}\n"
        text += f"━━━━━━━━━━━━━━━━━\n"
        text += f"💳 UPI: <code>{get('upi_id')}</code>\n"
        text += f"🔗 Link: <code>{get('access_link')}</code>"
        
        send(chat_id, text, dashboard_keyboard())
        return

    if data == "plans:list":
        answer()
        plans_list = plans(False)
        text = "💰 <b>Plans</b>\n━━━━━━━━━━━━━━━━━\n"
        for p in plans_list:
            text += f"🆔 {p['id']} | {p['label']} | ₹{int(p['price'])}\n"
        send(chat_id, text, {"inline_keyboard": [[{"text": "🔙 Dashboard", "callback_data": "dash"}]]})
        return

    if data == "pay:list":
        answer()
        with db() as c:
            rows = c.execute("SELECT * FROM payments WHERE status = 'pending' ORDER BY id DESC").fetchall()
        if not rows:
            return send(chat_id, "No pending payments.", {"inline_keyboard": [[{"text": "🔙 Dashboard", "callback_data": "dash"}]]})
        for r in rows[:5]:
            send(chat_id, f"🆔 #{r['order_code']}\n{r['plan_label']} — ₹{int(r['price'])}\n👤 {r['full_name']} (@{r['username']})",
                 review_keyboard(r["id"]))
        return

    if data == "settings":
        answer()
        send(chat_id, "⚙️ <b>Settings</b>\n\n"
             f"💳 UPI ID: <code>{get('upi_id')}</code>\n"
             f"🔗 Access Link: <code>{get('access_link')}</code>\n"
             f"📝 Welcome Text: {get('welcome_text')}",
             {"inline_keyboard": [
                 [{"text": "💳 Set UPI ID", "callback_data": "set_upi"}],
                 [{"text": "🔗 Set Access Link", "callback_data": "set_link"}],
                 [{"text": "📝 Set Welcome Text", "callback_data": "set_welcome"}],
                 [{"text": "🔙 Dashboard", "callback_data": "dash"}]
             ]})
        return

    if data == "bcast":
        set_step(chat_id, "bcast")
        answer()
        return send(chat_id, "📢 Send the message (text, photo or video) to broadcast to all users.",
                    {"inline_keyboard": [[{"text": "⬅️ Cancel", "callback_data": "dash"}]]})

    if data.startswith("pay_ok:") or data.startswith("pay_no:"):
        payment_id = data.split(":")[1]
        approve = data.startswith("pay_ok:")
        with db() as c:
            row = c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
            if not row or row["status"] != "pending":
                return answer("Already processed!")
            c.execute("UPDATE payments SET status = ? WHERE id = ?", ("approved" if approve else "declined", payment_id))
            order_code = row["order_code"]
            plan_label = row["plan_label"]
            price = row["price"]
            user_chat_id = int(row["chat_id"])
        
        if approve:
            link = get("access_link")
            send(user_chat_id, f"✅ Payment Approved!\n\n🆔 #{order_code}\n{plan_label} — ₹{int(price)}\n🔗 <a href='{link}'>{link}</a>")
            answer("✅ Approved & link sent!")
        else:
            send(user_chat_id, f"❌ Payment Declined!\n\n🆔 #{order_code}\n{plan_label} — ₹{int(price)}\nPlease contact support.")
            answer("❌ Declined!")
        
        # Update admin message
        call("editMessageText", chat_id=chat_id, message_id=cq["message"]["message_id"],
             text=f"✅ APPROVED" if approve else f"❌ DECLINED", parse_mode="HTML")
        return

    if data.startswith("set_"):
        key = data.replace("set_", "")
        if key == "upi":
            msg = send(chat_id, "💳 Send your UPI ID:\nExample: <code>your-upi@paytm</code>")
            bot = None  # We need to handle this differently
        return

# ==================== MAIN ====================
def first_run_setup():
    if not get("bot_token"):
        token = input("Bot token from @BotFather: ").strip()
        put("bot_token", token)

def main():
    init_db()
    first_run_setup()
    if not get("bot_token"):
        sys.exit("No bot token configured.")

    call("deleteWebhook", drop_pending_updates=False)
    me = call("getMe")
    if not me.get("ok"):
        sys.exit("Invalid bot token.")
    
    print(f"✅ Bot @{me['result'].get('username')} running.")
    print(f"👑 Owners: {OWNER_IDS}")
    print(f"💳 UPI ID: {get('upi_id')}")
    print("Press Ctrl+C to stop.")

    offset = 0
    while True:
        try:
            res = requests.get(
                f"{API}/bot{get('bot_token')}/getUpdates",
                params={"timeout": 50, "offset": offset,
                        "allowed_updates": json.dumps(["message", "callback_query"])},
                timeout=70,
            ).json()
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    if "message" in upd:
                        handle_message(upd["message"])
                    elif "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                except Exception as exc:
                    print("[error]", exc)
        except KeyboardInterrupt:
            print("\nStopped.")
            return
        except Exception as exc:
            print("[poll error]", exc)
            time.sleep(3)

if __name__ == "__main__":
    main()
