import os
import json
import sqlite3
import sys
import time
import random
import urllib.parse
import requests
import qrcode
from io import BytesIO
from PIL import Image

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")
API = "https://api.telegram.org"

# ==================== MULTI-OWNER CONFIG ====================
BOT_TOKEN = "8893379278:AAEOIQF5fdrGtWqikRDr2_hiBxbBjjzKlLM"
OWNER_IDS = [7130712170, 8754004223]
MEDIA_LIMIT = 10

DEFAULTS = {
    "bot_token": BOT_TOKEN,
    "admin_chat_id": str(OWNER_IDS[0]),
    "upi_id": "your-upi@paytm",
    "welcome_text": "🔥 Welcome to Zeta Store!\nChoose your plan below.",
    "access_link": "https://your-access-link.com",
    "qr_text": "Scan QR to pay",
    "custom_qr_file_id": "",
    "submitted_text": "✅ Request Submitted!\n\n🆔 Order #{order}\n⏳ Your plan will be activated after verification.",
    "approved_text": "✅ Payment Approved!\n\n🆔 Order #{order} — Plan: {plan}\nHere is your access link:",
    "declined_text": "❌ Payment Not Verified\n\n🆔 Order #{order} — Plan: {plan}\nPlease contact support.",
}

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
        c.execute("""CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            kind TEXT NOT NULL,
            file_id TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0)""")
        c.execute("CREATE TABLE IF NOT EXISTS state (chat_id TEXT PRIMARY KEY, step TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS user_messages (chat_id TEXT, message_id INTEGER, PRIMARY KEY (chat_id, message_id))")
        
        for k, v in DEFAULTS.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
        if not c.execute("SELECT COUNT(*) AS n FROM plans").fetchone()["n"]:
            plans_data = [
                ("Real Indian Desi Porn ✨", 199, "Pay ₹199 on the QR above and send the payment screenshot here.", 1),
                ("CHILD CORN", 149, "Pay ₹149 on the QR above and send the payment screenshot here.", 2),
                ("GORE R@PE", 39, "Pay ₹39 on the QR above and send the payment screenshot here.", 3),
                ("ALL VIDEOS VIP MEMBER", 39, "Pay ₹39 on the QR above and send the payment screenshot here.", 4),
                ("BHAI BHEN HOT", 39, "Pay ₹39 on the QR above and send the payment screenshot here.", 5),
                ("HOT DESI BHABHI", 39, "Pay ₹39 on the QR above and send the payment screenshot here.", 6),
                ("INFLUENCER50%OFF", 39, "Pay ₹39 on the QR above and send the payment screenshot here.", 7),
                ("BAAPBETI", 39, "Pay ₹39 on the QR above and send the payment screenshot here.", 8),
                ("VIP PLAN 1 LAKH VIDEO", 39, "Pay ₹39 on the QR above and send the payment screenshot here.", 9),
            ]
            c.executemany(
                "INSERT INTO plans (label, price, reply_text, position) VALUES (?, ?, ?, ?)",
                plans_data
            )

def get(key):
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULTS.get(key, "")

def put(key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

def get_plans(active_only=True):
    q = "SELECT * FROM plans" + (" WHERE active = 1" if active_only else "") + " ORDER BY position, id"
    with db() as c:
        return [dict(r) for r in c.execute(q).fetchall()]

def add_plan(label, price, reply_text=""):
    with db() as c:
        c.execute("INSERT INTO plans (label, price, reply_text, position) VALUES (?, ?, ?, ?)",
                  (label, price, reply_text, 99))
        return c.lastrowid

def update_plan(pid, label=None, price=None, reply_text=None, active=None):
    with db() as c:
        if label is not None:
            c.execute("UPDATE plans SET label = ? WHERE id = ?", (label, pid))
        if price is not None:
            c.execute("UPDATE plans SET price = ? WHERE id = ?", (price, pid))
        if reply_text is not None:
            c.execute("UPDATE plans SET reply_text = ? WHERE id = ?", (reply_text, pid))
        if active is not None:
            c.execute("UPDATE plans SET active = ? WHERE id = ?", (active, pid))

def delete_plan(pid):
    with db() as c:
        c.execute("DELETE FROM plans WHERE id = ?", (pid,))

def get_payment_by_order(order_code):
    with db() as c:
        return c.execute("SELECT * FROM payments WHERE order_code = ?", (order_code,)).fetchone()

def update_payment_status(order_code, status):
    with db() as c:
        c.execute("UPDATE payments SET status = ? WHERE order_code = ?", (status, order_code))

def all_chat_ids():
    with db() as c:
        return [r["chat_id"] for r in c.execute("SELECT DISTINCT chat_id FROM payments").fetchall()]

# ==================== MESSAGE CLEANUP FUNCTIONS ====================
def save_message(chat_id, message_id):
    """Save message ID for cleanup"""
    with db() as c:
        c.execute("INSERT OR IGNORE INTO user_messages (chat_id, message_id) VALUES (?, ?)", 
                  (str(chat_id), message_id))

def delete_previous_messages(chat_id):
    """Delete all previous messages for a user"""
    with db() as c:
        messages = c.execute("SELECT message_id FROM user_messages WHERE chat_id = ?", 
                            (str(chat_id),)).fetchall()
        for msg in messages:
            try:
                call("deleteMessage", chat_id=chat_id, message_id=msg["message_id"])
            except:
                pass
        c.execute("DELETE FROM user_messages WHERE chat_id = ?", (str(chat_id),))

def send_clean(chat_id, text, keyboard=None, parse_mode="HTML"):
    """Send message after cleaning previous ones"""
    delete_previous_messages(chat_id)
    result = send(chat_id, text, keyboard, parse_mode)
    if result and result.get("ok"):
        msg_id = result.get("result", {}).get("message_id")
        if msg_id:
            save_message(chat_id, msg_id)
    return result

def send_photo_clean(chat_id, file_path, caption="", keyboard=None):
    """Send photo after cleaning previous messages"""
    delete_previous_messages(chat_id)
    result = send_photo(chat_id, file_path, caption, keyboard)
    if result and result.get("ok"):
        msg_id = result.get("result", {}).get("message_id")
        if msg_id:
            save_message(chat_id, msg_id)
    return result

def send_media_group_clean(chat_id, items, caption=""):
    """Send media group after cleaning previous messages"""
    delete_previous_messages(chat_id)
    result = send_media_group(chat_id, items, caption)
    if result and result.get("ok"):
        # Media group returns array of messages
        for msg in result.get("result", []):
            if msg.get("message_id"):
                save_message(chat_id, msg["message_id"])
    return result

# ==================== MEDIA FUNCTIONS ====================
def media_list(scope):
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM media WHERE scope = ? ORDER BY position, id", (scope,)
        ).fetchall()]

def media_add(scope, kind, file_id):
    with db() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM media WHERE scope = ?", (scope,)).fetchone()["n"]
        if n >= MEDIA_LIMIT:
            return False
        c.execute("INSERT INTO media (scope, kind, file_id, position) VALUES (?, ?, ?, ?)",
                  (scope, kind, file_id, n + 1))
    return True

def media_clear(scope):
    with db() as c:
        c.execute("DELETE FROM media WHERE scope = ?", (scope,))

def send_media_group(chat_id, items, caption=""):
    items = items[:MEDIA_LIMIT]
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

# ==================== UPI QR GENERATOR (WITH QRCODE LIBRARY) ====================
def generate_upi_qr(upi_id, amount, order_id, name="Store"):
    """Generate QR code with dynamic amount using qrcode library"""
    upi_link = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR&tn=Order_{order_id}"
    
    try:
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(upi_link)
        qr.make(fit=True)
        
        # Create image with custom colors
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to bytes
        qr_bytes = BytesIO()
        img.save(qr_bytes, format='PNG')
        qr_bytes.seek(0)
        
        # Save to file
        qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"qr_{order_id}.png")
        with open(qr_path, 'wb') as f:
            f.write(qr_bytes.getvalue())
        
        return qr_path
    except Exception as e:
        print(f"QR generation error: {e}")
        # Fallback to API method
        try:
            encoded = urllib.parse.quote(upi_link, safe='')
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={encoded}"
            response = requests.get(qr_url, timeout=30)
            qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"qr_{order_id}.png")
            with open(qr_path, 'wb') as f:
                f.write(response.content)
            return qr_path
        except:
            return None

def new_order_code():
    with db() as c:
        for _ in range(50):
            code = str(random.randint(1000, 9999))
            if not c.execute("SELECT 1 FROM payments WHERE order_code = ?", (code,)).fetchone():
                return code
    return str(random.randint(1000, 9999))

def set_step(chat_id, step):
    with db() as c:
        if step:
            c.execute("INSERT OR REPLACE INTO state (chat_id, step) VALUES (?, ?)", (str(chat_id), step))
        else:
            c.execute("DELETE FROM state WHERE chat_id = ?", (str(chat_id),))

def get_step(chat_id):
    with db() as c:
        row = c.execute("SELECT step FROM state WHERE chat_id = ?", (str(chat_id),)).fetchone()
    return row["step"] if row else ""

# ==================== TELEGRAM FUNCTIONS ====================
def call(method, **payload):
    token = get("bot_token")
    res = requests.post(f"{API}/bot{token}/{method}", json=payload, timeout=90)
    data = res.json()
    if not data.get("ok"):
        print(f"[telegram] {method} failed: {data.get('description')}")
    return data

def send(chat_id, text, keyboard=None, parse_mode="HTML"):
    args = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if keyboard:
        args["reply_markup"] = keyboard
    return call("sendMessage", **args)

def send_photo(chat_id, file_path, caption="", keyboard=None):
    if isinstance(file_path, str) and os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            args = {"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"}
            if keyboard:
                args["reply_markup"] = keyboard
            return requests.post(f"{API}/bot{get('bot_token')}/sendPhoto", data=args, files={"photo": f}).json()
    if file_path and not os.path.exists(file_path):
        args = {"chat_id": chat_id, "photo": file_path, "caption": caption[:1024], "parse_mode": "HTML"}
        if keyboard:
            args["reply_markup"] = keyboard
        return call("sendPhoto", **args)
    return None

def render(template, order="", plan=""):
    return (template or "").replace("{order}", str(order)).replace("{plan}", str(plan))

def notify(chat_id, text_key, order="", plan="", extra=""):
    body = render(get(text_key), order, plan) + (("\n" + extra) if extra else "")
    return send_clean(chat_id, body)

def is_admin(chat_id):
    return int(chat_id) in OWNER_IDS

def extract_media(msg):
    if msg.get("photo"):
        return "photo", msg["photo"][-1]["file_id"]
    if msg.get("video"):
        return "video", msg["video"]["file_id"]
    if msg.get("animation"):
        return "video", msg["animation"]["file_id"]
    doc = msg.get("document") or {}
    if str(doc.get("mime_type", "")).startswith("video/"):
        return "video", doc["file_id"]
    if str(doc.get("mime_type", "")).startswith("image/"):
        return "photo", doc["file_id"]
    return None, ""

# ==================== 🔥 KEYBOARDS (FIXED) ====================

def start_keyboard():
    """Main menu — NO 💳 emoji, shortened long names"""
    rows = []
    for p in get_plans():
        label = p['label']
        # 🔥 Shorten long names for button (max 22 chars)
        if len(label) > 22:
            display_label = label[:20] + ".."
        else:
            display_label = label
        rows.append([{"text": f"{display_label} — ₹{int(p['price'])}", "callback_data": f"plan:{p['id']}"}])
    return {"inline_keyboard": rows}

def plan_detail_keyboard(pid):
    return {
        "inline_keyboard": [
            [{"text": "💳 Buy Now", "callback_data": f"buy:{pid}"}],
            [{"text": "🔙 Back", "callback_data": "back"}],
        ]
    }

def payment_keyboard(pid):
    return {
        "inline_keyboard": [
            [{"text": "✅ Check Payment Status", "callback_data": f"check:{pid}"}],
            [{"text": "❌ Cancel Payment", "callback_data": f"cancel_pay:{pid}"}],
        ]
    }

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
            [{"text": "📝 Pending", "callback_data": "pay:list"},
             {"text": "⚙️ Settings", "callback_data": "settings"}],
            [{"text": "📢 Broadcast", "callback_data": "bcast"},
             {"text": "🎞 Welcome Media", "callback_data": "media:welcome"}],
        ]
    }

def settings_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "💳 Set UPI ID", "callback_data": "set_upi"},
             {"text": "🖼 Upload Custom QR", "callback_data": "set_custom_qr"}],
            [{"text": "🔗 Set Access Link", "callback_data": "set_link"},
             {"text": "📝 Set QR Text", "callback_data": "set_qr_text"}],
            [{"text": "📝 Set Welcome Text", "callback_data": "set_welcome_text"}],
            [{"text": "🔙 Dashboard", "callback_data": "dash"}],
        ]
    }

def media_keyboard(scope):
    items = media_list(scope)
    return {
        "inline_keyboard": [
            [{"text": f"➕ Add photo/video ({len(items)}/{MEDIA_LIMIT})", "callback_data": f"madd:{scope}"}],
            [{"text": "🗑 Remove all", "callback_data": f"mclr:{scope}"}],
            [{"text": "🔙 Dashboard", "callback_data": "dash"}],
        ]
    }

def plans_admin_keyboard():
    rows = []
    for p in get_plans(False):
        rows.append([{"text": f"✏️ {p['label']} — ₹{int(p['price'])}", "callback_data": f"pedit:{p['id']}"}])
    rows.append([{"text": "➕ Add Plan", "callback_data": "pnew"}])
    rows.append([{"text": "🔙 Dashboard", "callback_data": "dash"}])
    return {"inline_keyboard": rows}

def plan_edit_keyboard(pid):
    with db() as c:
        p = c.execute("SELECT * FROM plans WHERE id = ?", (pid,)).fetchone()
    if not p:
        return {"inline_keyboard": [[{"text": "🔙 Plans", "callback_data": "plans:list"}]]}
    
    return {
        "inline_keyboard": [
            [{"text": f"✏️ Label: {p['label']}", "callback_data": f"pset:label:{pid}"}],
            [{"text": f"💵 Price: ₹{int(p['price'])}", "callback_data": f"pset:price:{pid}"}],
            [{"text": f"📝 Reply: {p['reply_text'][:18] + '..' if len(p['reply_text']) > 18 else p['reply_text']}", "callback_data": f"pset:reply_text:{pid}"}],
            [{"text": "🎞 Plan Media", "callback_data": f"media:plan:{pid}"}],
            [{"text": "🗑 Delete Plan", "callback_data": f"pdel:{pid}"}],
            [{"text": "🔙 Plans", "callback_data": "plans:list"}],
        ]
    }

# ==================== HANDLERS ====================
def handle_message(msg):
    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return
    frm = msg.get("from", {}) or {}
    text = (msg.get("text") or msg.get("caption") or "").strip()
    kind, file_id = extract_media(msg)
    step = get_step(chat_id)

    # Admin: Add media (welcome or plan)
    if step and step.startswith("madd:") and is_admin(chat_id):
        scope = step.replace("madd:", "")
        if not file_id:
            return send_clean(chat_id, "Send a photo or video, please.")
        ok = media_add(scope, kind, file_id)
        if not ok:
            set_step(chat_id, "")
            return send_clean(chat_id, f"Limit reached ({MEDIA_LIMIT}).", media_keyboard(scope))
        n = len(media_list(scope))
        return send_clean(chat_id, f"Added ✅ ({n}/{MEDIA_LIMIT}). Send another or tap Done.",
                    {"inline_keyboard": [[{"text": "✔️ Done", "callback_data": f"mdone:{scope}"}]]})

    # Admin: Set value
    if step and step.startswith("set:") and is_admin(chat_id):
        key = step.replace("set:", "")
        put(key, text)
        set_step(chat_id, "")
        return send_clean(chat_id, f"✅ {key} updated:\n<code>{text}</code>", dashboard_keyboard())

    # Admin: Set custom QR (photo upload)
    if step == "set_custom_qr" and is_admin(chat_id):
        if not file_id or kind != "photo":
            return send_clean(chat_id, "❌ Please send a photo (QR image).")
        put("custom_qr_file_id", file_id)
        set_step(chat_id, "")
        return send_clean(chat_id, "✅ Custom QR uploaded successfully!", dashboard_keyboard())

    # Admin: Edit plan field
    if step and step.startswith("pset:") and is_admin(chat_id):
        _, field, pid = step.split(":")
        
        if field == "price":
            try:
                value = float(text)
            except:
                return send_clean(chat_id, "❌ Invalid price. Send a number.")
        else:
            value = text
        
        update_plan(int(pid), **{field: value})
        set_step(chat_id, "")
        
        with db() as c:
            p = c.execute("SELECT * FROM plans WHERE id = ?", (pid,)).fetchone()
        
        return send_clean(chat_id, f"✅ {field} updated!\n\n🔹 New Value: <code>{p[field]}</code>", plan_edit_keyboard(pid))

    # Payment screenshot
    if file_id and kind == "photo" and not is_admin(chat_id):
        with db() as c:
            sel = c.execute("SELECT * FROM payments WHERE chat_id = ? AND status = 'selected' ORDER BY id DESC LIMIT 1", (str(chat_id),)).fetchone()
            if sel:
                c.execute("UPDATE payments SET photo_file_id = ?, status = 'pending' WHERE id = ?", (file_id, sel["id"]))
                order_code = sel["order_code"]
                label = sel["plan_label"]
                price = sel["price"]
            else:
                return send_clean(chat_id, "❌ No pending payment. Select a plan with /start")
        
        notify(chat_id, "submitted_text", order_code, label)
        who = "@" + frm.get("username", "") if frm.get("username") else frm.get("first_name", str(chat_id))
        for admin_id in OWNER_IDS:
            try:
                send_photo(admin_id, file_id,
                           caption=f"🧾 Payment\n🆔 #{order_code}\n{label} — ₹{int(price)}\nFrom: {who}",
                           keyboard=review_keyboard(sel["id"]))
            except:
                pass
        return

    # UTR / Text
    if text and not text.startswith("/") and not is_admin(chat_id):
        with db() as c:
            sel = c.execute("SELECT * FROM payments WHERE chat_id = ? AND status = 'selected' ORDER BY id DESC LIMIT 1", (str(chat_id),)).fetchone()
            if sel:
                c.execute("UPDATE payments SET status = 'pending' WHERE id = ?", (sel["id"],))
                notify(chat_id, "submitted_text", sel["order_code"], sel["plan_label"])
                for admin_id in OWNER_IDS:
                    try:
                        send(admin_id, f"🧾 UTR\n🆔 #{sel['order_code']}\n{sel['plan_label']} — ₹{int(sel['price'])}\nUTR: <code>{text}</code>",
                             review_keyboard(sel["id"]))
                    except:
                        pass
                return

    # Commands
    if text.startswith("/start"):
        items = media_list("welcome")
        if items:
            send_media_group_clean(chat_id, items, get("welcome_text"))
        else:
            send_clean(chat_id, get("welcome_text"))
        return send_clean(chat_id, "Choose a plan 👇", start_keyboard())

    if text.startswith("/admin") or text.startswith("/dashboard"):
        if is_admin(chat_id):
            return send_clean(chat_id, "👑 Admin Panel", dashboard_keyboard())
        return send_clean(chat_id, "❌ Not authorized")

    send_clean(chat_id, "Send /start")

def handle_callback(cq):
    cq_id = cq["id"]
    data = cq.get("data") or ""
    frm = cq.get("from", {}) or {}
    chat_id = cq.get("message", {}).get("chat", {}).get("id")

    def answer(text=""):
        call("answerCallbackQuery", callback_query_id=cq_id, text=text)

    # ==================== PLAN SELECT (FULL NAME) ====================
    if data.startswith("plan:"):
        answer()
        pid = data.split(":")[1]
        with db() as c:
            p = c.execute("SELECT * FROM plans WHERE id = ?", (pid,)).fetchone()
        if not p:
            return
        
        # Plan media
        items = media_list(f"plan:{pid}")
        if items:
            send_media_group_clean(chat_id, items, f"<b>{p['label']}</b> — ₹{int(p['price'])}")
        
        # 🔥 Full name (not shortened)
        text = f"✅ <b>{p['label']}</b>\n"
        text += f"💰 Price: ₹{int(p['price'])}\n"
        text += f"📝 {p['reply_text'] or 'Pay via UPI'}\n\n"
        text += "Click Buy Now to proceed."
        
        send_clean(chat_id, text, plan_detail_keyboard(pid))
        return

    # ==================== BUY NOW ====================
    if data.startswith("buy:"):
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
        custom_qr = get("custom_qr_file_id")
        
        caption = f"✅ <b>{p['label']}</b>\n"
        caption += f"🆔 Order #{order_code}\n"
        caption += f"💰 Amount: ₹{int(p['price'])}\n"
        caption += f"💳 UPI: <code>{upi_id}</code>\n\n"
        caption += f"{get('qr_text')}\n\n"
        caption += "After payment, tap ✅ Check Payment Status"
        
        if custom_qr:
            send_photo_clean(chat_id, custom_qr, caption, payment_keyboard(pid))
        else:
            qr_path = generate_upi_qr(upi_id, p["price"], order_code)
            if qr_path and os.path.exists(qr_path):
                send_photo_clean(chat_id, qr_path, caption, payment_keyboard(pid))
                try: os.remove(qr_path)
                except: pass
            else:
                send_clean(chat_id, "QR generation failed.", payment_keyboard(pid))
        return

    # ==================== CHECK PAYMENT STATUS ====================
    if data.startswith("check:"):
        answer()
        pid = data.split(":")[1]
        with db() as c:
            p = c.execute("SELECT * FROM plans WHERE id = ?", (pid,)).fetchone()
        if not p:
            return
        
        send_clean(chat_id, "📸 Kindly send payment screenshot to verify", pay_keyboard(pid))
        return

    # ==================== CANCEL PAYMENT ====================
    if data.startswith("cancel_pay:"):
        answer("Cancelled ❌")
        with db() as c:
            c.execute("DELETE FROM payments WHERE chat_id = ? AND status = 'selected'", (str(chat_id),))
        return send_clean(chat_id, "❌ Payment cancelled. Use /start to choose a plan.")

    # ==================== I HAVE PAID ====================
    if data.startswith("paid:"):
        answer("Send screenshot or UTR")
        return send_clean(chat_id, "✅ Great!\n\n📸 Send payment screenshot, or\n📝 Type UTR / Transaction ID")

    # ==================== BACK ====================
    if data == "back":
        answer()
        items = media_list("welcome")
        if items:
            send_media_group_clean(chat_id, items, get("welcome_text"))
        else:
            send_clean(chat_id, get("welcome_text"))
        return send_clean(chat_id, "Choose a plan 👇", start_keyboard())

    # ==================== CANCEL ====================
    if data == "cancel":
        answer("Cancelled")
        with db() as c:
            c.execute("DELETE FROM payments WHERE chat_id = ? AND status = 'selected'", (str(chat_id),))
        return send_clean(chat_id, "Cancelled. /start")

    # ==================== ADMIN ====================
    if not is_admin(frm.get("id")):
        return answer("Only admin!")

    if data == "dash":
        answer()
        with db() as c:
            payments = c.execute("SELECT * FROM payments").fetchall()
            pending = [p for p in payments if p["status"] == "pending"]
            approved = [p for p in payments if p["status"] == "approved"]
            declined = [p for p in payments if p["status"] == "declined"]
            revenue = sum(p["price"] for p in approved)
        
        text = f"📊 Dashboard\n━━━━━━━━━━━\n"
        text += f"👥 Users: {len(set(p['chat_id'] for p in payments))}\n"
        text += f"🧾 Pending: {len(pending)}\n"
        text += f"✅ Approved: {len(approved)}\n"
        text += f"❌ Declined: {len(declined)}\n"
        text += f"💰 Revenue: ₹{int(revenue)}\n"
        text += f"━━━━━━━━━━━\n"
        text += f"💳 UPI: <code>{get('upi_id')}</code>"
        send_clean(chat_id, text, dashboard_keyboard())
        return

    if data == "media:welcome":
        answer()
        items = media_list("welcome")
        if items:
            send_media_group_clean(chat_id, items, "🎞 Welcome Media")
        return send_clean(chat_id, f"Welcome media: {len(items)}/{MEDIA_LIMIT} items.", media_keyboard("welcome"))

    if data.startswith("media:plan:"):
        pid = data.split(":")[2]
        scope = f"plan:{pid}"
        items = media_list(scope)
        if items:
            send_media_group_clean(chat_id, items, "🎞 Plan Media")
        return send_clean(chat_id, f"Plan media: {len(items)}/{MEDIA_LIMIT} items.", media_keyboard(scope))

    if data.startswith("madd:"):
        scope = data.split(":", 1)[1]
        set_step(chat_id, f"madd:{scope}")
        answer()
        return send_clean(chat_id, f"Send photos/videos (up to {MEDIA_LIMIT}). Tap Done when finished.",
                    {"inline_keyboard": [[{"text": "✔️ Done", "callback_data": f"mdone:{scope}"}]]})

    if data.startswith("mdone:"):
        scope = data.split(":", 1)[1]
        set_step(chat_id, "")
        answer("Done")
        return send_clean(chat_id, "Media saved ✅", media_keyboard(scope))

    if data.startswith("mclr:"):
        scope = data.split(":", 1)[1]
        media_clear(scope)
        answer("Removed")
        return send_clean(chat_id, "All media removed.", media_keyboard(scope))

    if data == "plans:list":
        answer()
        plans = get_plans(False)
        if not plans:
            return send_clean(chat_id, "No plans.", {"inline_keyboard": [[{"text": "➕ Add Plan", "callback_data": "pnew"}]]})
        text = "💰 Plans\n━━━━━━━━━━━\n"
        for p in plans:
            status = "🟢" if p["active"] else "🔴"
            text += f"{status} {p['id']}. {p['label']} — ₹{int(p['price'])}\n"
        send_clean(chat_id, text, plans_admin_keyboard())
        return

    if data == "pnew":
        set_step(chat_id, "pnew")
        answer()
        return send_clean(chat_id, "📝 Send plan details:\n<code>Label|Price</code>\nExample: <code>Gold Plan|199</code>")

    if data.startswith("pedit:"):
        pid = data.split(":")[1]
        answer()
        return send_clean(chat_id, f"Editing plan #{pid}", plan_edit_keyboard(pid))

    if data.startswith("pset:"):
        _, field, pid = data.split(":")
        
        with db() as c:
            p = c.execute("SELECT * FROM plans WHERE id = ?", (pid,)).fetchone()
        
        if not p:
            return answer("Plan not found!")
        
        set_step(chat_id, f"pset:{field}:{pid}")
        answer()
        
        prompts = {
            "label": f"📝 <b>Current Label:</b>\n<code>{p['label']}</code>\n\n✏️ Send new label (you can add emojis):",
            "price": f"💵 <b>Current Price:</b>\n<code>₹{int(p['price'])}</code>\n\n✏️ Send new price:",
            "reply_text": f"📝 <b>Current Reply Text:</b>\n<code>{p['reply_text'] or '(empty)'}</code>\n\n✏️ Send new reply text (you can add emojis):",
        }
        return send_clean(chat_id, prompts.get(field, "Send new value"))

    if data.startswith("pdel:"):
        pid = data.split(":")[1]
        delete_plan(pid)
        answer("Deleted")
        return send_clean(chat_id, "Plan deleted.", plans_admin_keyboard())

    if data == "pay:list":
        answer()
        with db() as c:
            rows = c.execute("SELECT * FROM payments WHERE status = 'pending' ORDER BY id DESC").fetchall()
        if not rows:
            return send_clean(chat_id, "No pending.", {"inline_keyboard": [[{"text": "🔙 Dashboard", "callback_data": "dash"}]]})
        for r in rows[:5]:
            send_clean(chat_id, f"🆔 #{r['order_code']}\n{r['plan_label']} — ₹{int(r['price'])}\n👤 {r['full_name']}",
                 review_keyboard(r["id"]))
        return

    if data == "settings":
        answer()
        send_clean(chat_id, f"⚙️ Settings\n\n💳 UPI: <code>{get('upi_id')}</code>\n🔗 Link: <code>{get('access_link')}</code>\n📝 QR Text: <code>{get('qr_text')}</code>\n🖼 Custom QR: {'✅' if get('custom_qr_file_id') else '❌'}",
             settings_keyboard())
        return

    if data == "bcast":
        set_step(chat_id, "bcast")
        answer()
        return send_clean(chat_id, "📢 Send broadcast message.",
                    {"inline_keyboard": [[{"text": "⬅️ Cancel", "callback_data": "dash"}]]})

    if data.startswith("pay_ok:") or data.startswith("pay_no:"):
        pid = data.split(":")[1]
        approve = data.startswith("pay_ok:")
        with db() as c:
            row = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
            if not row or row["status"] != "pending":
                return answer("Already done!")
            c.execute("UPDATE payments SET status = ? WHERE id = ?", ("approved" if approve else "declined", pid))
            order_code = row["order_code"]
            plan = row["plan_label"]
            price = row["price"]
            user_chat_id = int(row["chat_id"])
        
        if approve:
            link = get("access_link")
            send_clean(user_chat_id, f"✅ Approved!\n🆔 #{order_code}\n{plan} — ₹{int(price)}\n🔗 <a href='{link}'>{link}</a>")
            answer("✅ Approved!")
        else:
            send_clean(user_chat_id, f"❌ Declined!\n🆔 #{order_code}\n{plan} — ₹{int(price)}")
            answer("❌ Declined!")
        
        call("editMessageText", chat_id=chat_id, message_id=cq["message"]["message_id"],
             text="✅ APPROVED" if approve else "❌ DECLINED", parse_mode="HTML")
        return

    if data == "set_welcome_text":
        set_step(chat_id, "set:welcome_text")
        answer()
        return send_clean(chat_id, "📝 Send your new welcome text.\n\nYou can use emojis and HTML formatting.")

    if data == "set_custom_qr":
        set_step(chat_id, "set_custom_qr")
        answer()
        return send_clean(chat_id, "🖼 Send your custom QR image (photo).\n\nThis QR will be shown to all users.")

    if data.startswith("set_"):
        key = data.replace("set_", "")
        set_step(chat_id, f"set:{key}")
        answer()
        prompts = {
            "upi": "Send UPI ID (e.g., your-upi@paytm)",
            "link": "Send Access Link",
            "qr_text": "Send QR text",
        }
        return send_clean(chat_id, prompts.get(key, "Send value"))

# ==================== MAIN ====================
def first_run_setup():
    if not get("bot_token"):
        token = input("Bot token: ").strip()
        put("bot_token", token)

def main():
    init_db()
    first_run_setup()
    if not get("bot_token"):
        sys.exit("No token")

    call("deleteWebhook", drop_pending_updates=False)
    me = call("getMe")
    if not me.get("ok"):
        sys.exit("Invalid token")
    
    print(f"✅ Bot @{me['result'].get('username')} running")
    print(f"👑 Owners: {OWNER_IDS}")
    print(f"💳 UPI: {get('upi_id')}")
    print("Press Ctrl+C to stop")

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
