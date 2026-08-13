"""
Telegram Payment Bot — Simple Version
- No Mini App
- No extra files
- Admin commands in Telegram only
- Dynamic UPI QR Generator
- Multi-owner support
"""

import os
import json
import sqlite3
import time
import random
import requests
import urllib.parse
from datetime import datetime

# ==================== CONFIG ====================
BOT_TOKEN = "8708150884:AAHA7Wn3dddxzyc1cEzKRpA3pXtj-DWv3EY"
ADMIN_IDS = [8754004223, 7130712170]  # Multiple owners
DB_PATH = "bot.db"

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Settings table
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # Plans table
    c.execute('''CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT,
        price REAL,
        active INTEGER DEFAULT 1
    )''')
    
    # Payments table
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT,
        chat_id TEXT,
        username TEXT,
        full_name TEXT,
        plan_label TEXT,
        price REAL,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )''')
    
    # Default settings
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('upi_id', 'your-upi@paytm')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('access_link', 'https://your-link.com')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', 'Welcome to Payment Bot!')")
    
    # Default plans
    c.execute("SELECT COUNT(*) FROM plans")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO plans (label, price) VALUES ('Basic Plan', 49)")
        c.execute("INSERT INTO plans (label, price) VALUES ('Premium Plan', 99)")
    
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_plans():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM plans WHERE active = 1 ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return rows

def get_payments(status=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if status:
        c.execute("SELECT * FROM payments WHERE status = ? ORDER BY id DESC", (status,))
    else:
        c.execute("SELECT * FROM payments ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def add_payment(chat_id, username, full_name, plan_label, price):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    order_code = str(random.randint(1000, 9999))
    c.execute("INSERT INTO payments (order_code, chat_id, username, full_name, plan_label, price, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (order_code, str(chat_id), username or "", full_name or "", plan_label, price, "pending", datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return order_code

def update_payment_status(order_code, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE payments SET status = ? WHERE order_code = ?", (status, order_code))
    conn.commit()
    conn.close()

def get_payment_by_order(order_code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE order_code = ?", (order_code,))
    row = c.fetchone()
    conn.close()
    return row

# ==================== UPI QR GENERATOR ====================
def generate_upi_qr(upi_id, amount, order_id):
    upi_link = f"upi://pay?pa={upi_id}&pn=Store&am={amount}&cu=INR&tn=Order_{order_id}"
    encoded = urllib.parse.quote(upi_link, safe='')
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded}"
    return qr_url

# ==================== TELEGRAM BOT ====================
import telebot
from telebot import types

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ==================== START COMMAND ====================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    welcome_text = get_setting("welcome_text") or "Welcome to Payment Bot!"
    
    if is_admin(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📊 Dashboard", callback_data="dashboard"))
        markup.add(types.InlineKeyboardButton("💰 Plans", callback_data="plans"))
        markup.add(types.InlineKeyboardButton("📝 Payments", callback_data="payments"))
        bot.send_message(message.chat.id, f"👑 Admin Panel\n\n{welcome_text}", reply_markup=markup)
    else:
        markup = types.InlineKeyboardMarkup()
        plans = get_plans()
        for plan in plans:
            markup.add(types.InlineKeyboardButton(f"{plan[1]} — ₹{int(plan[2])}", callback_data=f"plan_{plan[0]}"))
        bot.send_message(message.chat.id, f"🛒 Choose a plan:\n\n{welcome_text}", reply_markup=markup)

# ==================== PLAN SELECT ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("plan_"))
def plan_callback(call):
    user_id = call.from_user.id
    plan_id = int(call.data.split("_")[1])
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
    plan = c.fetchone()
    conn.close()
    
    if not plan:
        bot.answer_callback_query(call.id, "Plan not found!")
        return
    
    label, price = plan[1], plan[2]
    order_code = add_payment(user_id, call.from_user.username, call.from_user.first_name, label, price)
    
    upi_id = get_setting("upi_id") or "your-upi@paytm"
    qr_url = generate_upi_qr(upi_id, price, order_code)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ I have paid", callback_data=f"paid_{order_code}"))
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    
    bot.send_photo(
        call.message.chat.id,
        qr_url,
        caption=f"✅ <b>{label}</b> — ₹{int(price)}\n\n"
                f"🆔 Order #{order_code}\n"
                f"💳 UPI: <code>{upi_id}</code>\n\n"
                f"Scan the QR or pay manually, then tap 'I have paid'.",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

# ==================== PAID CONFIRMATION ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("paid_"))
def paid_callback(call):
    order_code = call.data.split("_")[1]
    payment = get_payment_by_order(order_code)
    
    if not payment:
        bot.answer_callback_query(call.id, "Order not found!")
        return
    
    if payment[6] != "pending":
        bot.answer_callback_query(call.id, f"Already {payment[6]}!")
        return
    
    bot.send_message(
        call.message.chat.id,
        f"✅ Order #{order_code} received!\n\n"
        f"📸 Please send your payment screenshot or UTR number.\n\n"
        f"Admin will verify and approve it."
    )
    bot.answer_callback_query(call.id, "Waiting for screenshot...")

# ==================== PAYMENT SCREENSHOT ====================
@bot.message_handler(content_types=['photo'])
def handle_screenshot(message):
    user_id = message.from_user.id
    if is_admin(user_id):
        return
    
    # Check if user has pending payment
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE chat_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (str(user_id),))
    payment = c.fetchone()
    conn.close()
    
    if not payment:
        bot.reply_to(message, "❌ No pending payment found. Please select a plan first with /start")
        return
    
    order_code = payment[1]
    file_id = message.photo[-1].file_id
    
    # Forward to admin
    for admin_id in ADMIN_IDS:
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_code}"),
                types.InlineKeyboardButton("❌ Decline", callback_data=f"decline_{order_code}")
            )
            bot.send_photo(
                admin_id,
                file_id,
                caption=f"🧾 Payment Screenshot\n\n"
                        f"🆔 Order #{order_code}\n"
                        f"👤 {payment[4]} (@{payment[3] or 'N/A'})\n"
                        f"💳 {payment[5]} — ₹{int(payment[6])}\n\n"
                        f"Tap Approve or Decline:",
                reply_markup=markup
            )
        except:
            pass
    
    bot.reply_to(message, f"✅ Screenshot sent to admin!\n\n🆔 Order #{order_code}\n\nYou will be notified once approved.")

# ==================== APPROVE / DECLINE ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("decline_"))
def approve_decline_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin can do this!")
        return
    
    action, order_code = call.data.split("_")
    status = "approved" if action == "approve" else "declined"
    
    update_payment_status(order_code, status)
    payment = get_payment_by_order(order_code)
    
    if not payment:
        bot.answer_callback_query(call.id, "Order not found!")
        return
    
    user_id = int(payment[2])
    
    if status == "approved":
        access_link = get_setting("access_link") or "https://your-link.com"
        bot.send_message(
            user_id,
            f"✅ Payment Approved!\n\n🆔 Order #{order_code}\n💳 {payment[5]} — ₹{int(payment[6])}\n\n🔗 Access Link: <a href='{access_link}'>{access_link}</a>\n\nThank you!"
        )
        bot.send_message(
            call.message.chat.id,
            f"✅ Order #{order_code} approved!\n\nAccess link sent to user."
        )
    else:
        bot.send_message(
            user_id,
            f"❌ Payment Declined!\n\n🆔 Order #{order_code}\n\nPlease contact support for more details."
        )
        bot.send_message(
            call.message.chat.id,
            f"❌ Order #{order_code} declined!"
        )
    
    # Update admin message
    bot.edit_message_caption(
        caption=f"🧾 Payment {status.upper()}!\n\n🆔 Order #{order_code}\n✅ Approved" if status == "approved" else f"🧾 Payment {status.upper()}!\n\n🆔 Order #{order_code}\n❌ Declined",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.answer_callback_query(call.id, f"{status.capitalize()}!")

# ==================== CANCEL ====================
@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cancel_callback(call):
    bot.answer_callback_query(call.id, "Cancelled")
    bot.send_message(call.message.chat.id, "Cancelled. Use /start to choose a plan.")

# ==================== DASHBOARD ====================
@bot.callback_query_handler(func=lambda call: call.data == "dashboard")
def dashboard_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    payments = get_payments()
    pending = [p for p in payments if p[6] == "pending"]
    approved = [p for p in payments if p[6] == "approved"]
    declined = [p for p in payments if p[6] == "declined"]
    total_revenue = sum(p[6] for p in approved)
    
    text = f"""📊 <b>Dashboard</b>
━━━━━━━━━━━━━━━━━
👥 Total Customers: {len(set(p[2] for p in payments))}
🧾 Pending: {len(pending)}
✅ Approved: {len(approved)}
❌ Declined: {len(declined)}
💰 Revenue: ₹{int(total_revenue)}
━━━━━━━━━━━━━━━━━
💳 UPI ID: <code>{get_setting('upi_id')}</code>
🔗 Access Link: <code>{get_setting('access_link') or 'Not set'}</code>"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💰 Plans", callback_data="plans"))
    markup.add(types.InlineKeyboardButton("📝 Payments", callback_data="payments"))
    markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="dashboard"))
    markup.add(types.InlineKeyboardButton("⚙️ Settings", callback_data="settings"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

# ==================== PAYMENTS LIST ====================
@bot.callback_query_handler(func=lambda call: call.data == "payments")
def payments_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    payments = get_payments("pending")
    
    if not payments:
        text = "📝 No pending payments."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return
    
    text = "📝 <b>Pending Payments</b>\n━━━━━━━━━━━━━━━━━\n"
    for p in payments[:10]:
        text += f"🆔 #{p[1]} | {p[5]} | ₹{int(p[6])}\n"
        text += f"👤 {p[4]} (@{p[3] or 'N/A'})\n"
        text += f"━━━━━━━━━━━━━━━━━\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

# ==================== PLANS ====================
@bot.callback_query_handler(func=lambda call: call.data == "plans")
def plans_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    plans = get_plans()
    text = "💰 <b>Plans</b>\n━━━━━━━━━━━━━━━━━\n"
    for p in plans:
        text += f"🆔 {p[0]} | {p[1]} | ₹{int(p[2])}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Add Plan", callback_data="add_plan"))
    markup.add(types.InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

# ==================== SETTINGS ====================
@bot.callback_query_handler(func=lambda call: call.data == "settings")
def settings_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Set UPI ID", callback_data="set_upi"))
    markup.add(types.InlineKeyboardButton("🔗 Set Access Link", callback_data="set_link"))
    markup.add(types.InlineKeyboardButton("📝 Set Welcome Text", callback_data="set_welcome"))
    markup.add(types.InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard"))
    
    bot.edit_message_text("⚙️ <b>Settings</b>", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

# ==================== SET UPI ====================
@bot.callback_query_handler(func=lambda call: call.data == "set_upi")
def set_upi_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    msg = bot.send_message(call.message.chat.id, "💳 Send your UPI ID:\nExample: <code>your-upi@paytm</code>")
    bot.register_next_step_handler(msg, set_upi_step)
    bot.answer_callback_query(call.id)

def set_upi_step(message):
    if not is_admin(message.from_user.id):
        return
    upi_id = message.text.strip()
    set_setting("upi_id", upi_id)
    bot.reply_to(message, f"✅ UPI ID set to: <code>{upi_id}</code>")

# ==================== SET ACCESS LINK ====================
@bot.callback_query_handler(func=lambda call: call.data == "set_link")
def set_link_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    msg = bot.send_message(call.message.chat.id, "🔗 Send your Access Link:\nExample: <code>https://your-link.com</code>")
    bot.register_next_step_handler(msg, set_link_step)
    bot.answer_callback_query(call.id)

def set_link_step(message):
    if not is_admin(message.from_user.id):
        return
    link = message.text.strip()
    set_setting("access_link", link)
    bot.reply_to(message, f"✅ Access Link set to: <code>{link}</code>")

# ==================== SET WELCOME TEXT ====================
@bot.callback_query_handler(func=lambda call: call.data == "set_welcome")
def set_welcome_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    msg = bot.send_message(call.message.chat.id, "📝 Send your Welcome Text:")
    bot.register_next_step_handler(msg, set_welcome_step)
    bot.answer_callback_query(call.id)

def set_welcome_step(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip()
    set_setting("welcome_text", text)
    bot.reply_to(message, f"✅ Welcome Text set:\n\n{text}")

# ==================== ADD PLAN ====================
@bot.callback_query_handler(func=lambda call: call.data == "add_plan")
def add_plan_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admin!")
        return
    
    msg = bot.send_message(call.message.chat.id, "📝 Send plan details:\n<code>Label|Price</code>\nExample: <code>Gold Plan|199</code>")
    bot.register_next_step_handler(msg, add_plan_step)
    bot.answer_callback_query(call.id)

def add_plan_step(message):
    if not is_admin(message.from_user.id):
        return
    try:
        label, price = message.text.split("|")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO plans (label, price) VALUES (?, ?)", (label.strip(), float(price.strip())))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Plan added:\n{label.strip()} — ₹{int(float(price.strip()))}")
    except:
        bot.reply_to(message, "❌ Invalid format! Use: <code>Label|Price</code>")

# ==================== MAIN ====================
if __name__ == "__main__":
    init_db()
    print("✅ Bot started!")
    print(f"👑 Admins: {ADMIN_IDS}")
    print(f"💳 UPI ID: {get_setting('upi_id')}")
    bot.infinity_polling()
