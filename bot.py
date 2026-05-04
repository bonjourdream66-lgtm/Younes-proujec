import sqlite3
import time
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "PUT_YOUR_TOKEN_HERE"
ADMIN_ID = 123456789
TIMEOUT = 300

# ================= DATABASE =================

def db():
    return sqlite3.connect("bot.db", check_same_thread=False)

def init():
    conn = db()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        points INTEGER DEFAULT 0
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price INTEGER,
        file_id TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS states (
        user_id INTEGER PRIMARY KEY,
        state TEXT,
        data TEXT,
        updated_at REAL
    )""")

    conn.commit()
    conn.close()

init()

# ================= ECONOMY =================

def add_points(uid, amount):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET points = points + ? WHERE user_id=?", (amount, uid))
    conn.commit()
    conn.close()

def user(uid):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    u = cur.fetchone()

    if not u:
        cur.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        u = cur.fetchone()

    conn.close()
    return u

# ================= STATE SYSTEM =================

def set_state(uid, state, data=None):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO states VALUES (?, ?, ?, ?)
    """, (uid, state, json.dumps(data or {}), time.time()))

    conn.commit()
    conn.close()

def get_state(uid):
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT state, data, updated_at FROM states WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    if time.time() - row[2] > TIMEOUT:
        clear_state(uid)
        return None

    return {"state": row[0], "data": json.loads(row[1])}

def clear_state(uid):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM states WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

# ================= UI PAGES =================

def home():
    return "👤 الرئيسية", InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 المحفظة", callback_data="wallet")],
        [InlineKeyboardButton("🎮 الألعاب", callback_data="games")],
        [InlineKeyboardButton("🏆 الترتيب", callback_data="top")],
        [InlineKeyboardButton("👑 VIP", callback_data="vip")],
        [InlineKeyboardButton("⚙️ الأدمن", callback_data="admin")]
    ])

def wallet_page(u):
    return f"💰 نقاطك: {u[1]}", InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data="home")]
    ])

# ================= ADMIN PANEL =================

def admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 إضافة لعبة", callback_data="add_game")],
        [InlineKeyboardButton("📊 عرض الألعاب", callback_data="list_games")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="home")]
    ])

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user(uid)

    text, kb = home()
    await update.message.reply_text(text, reply_markup=kb)

# ================= CALLBACK ROUTER =================

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    data = q.data
    u = user(uid)

    # ===== HOME =====
    if data == "home":
        text, kb = home()

    elif data == "wallet":
        text, kb = wallet_page(u)

    elif data == "games":
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT id, name, price FROM games")
        rows = cur.fetchall()
        conn.close()

        text = "🎮 الألعاب:\n\n" + "\n".join([f"{r[0]} - {r[1]} 💰{r[2]}" for r in rows])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="home")]])

    elif data == "top":
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT user_id, points FROM users ORDER BY points DESC LIMIT 10")
        rows = cur.fetchall()
        conn.close()

        text = "🏆 الترتيب:\n\n" + "\n".join([f"{i+1}. {r[0]} - {r[1]}" for i,r in enumerate(rows)])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="home")]])

    elif data == "vip":
        text = "👑 VIP قريباً..."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="home")]])

    elif data == "admin":
        if uid != ADMIN_ID:
            text = "❌ غير مصرح"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="home")]])
        else:
            text = "👑 لوحة الأدمن"
            kb = admin_panel()

    # ===== ADMIN ACTIONS =====
    elif data == "add_game":
        set_state(uid, "NAME")
        text = "📝 أرسل اسم اللعبة"
        kb = None

    elif data == "list_games":
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM games")
        rows = cur.fetchall()
        conn.close()

        text = "🎮 الألعاب:\n\n" + "\n".join([f"{r[0]} - {r[1]} 💰{r[2]}" for r in rows])
        kb = admin_panel()

    else:
        text, kb = home()

    await q.message.edit_text(text, reply_markup=kb)

# ================= STEP SYSTEM =================

async def step_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = get_state(uid)

    if not st:
        return

    text = update.message.text

    # NAME
    if st["state"] == "NAME":
        st["data"]["name"] = text
        set_state(uid, "PRICE", st["data"])
        return await update.message.reply_text("💰 أرسل السعر")

    # PRICE
    if st["state"] == "PRICE":
        if not text.isdigit():
            return await update.message.reply_text("❌ رقم فقط")

        st["data"]["price"] = int(text)
        set_state(uid, "FILE", st["data"])
        return await update.message.reply_text("📦 أرسل الملف")

# ================= FILE =================

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = get_state(uid)

    if not st or st["state"] != "FILE":
        return

    file_id = update.message.document.file_id
    data = st["data"]

    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO games (name, price, file_id) VALUES (?, ?, ?)",
                (data["name"], data["price"], file_id))
    conn.commit()
    conn.close()

    clear_state(uid)

    await update.message.reply_text("✅ تم إضافة اللعبة")

# ================= RUN =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(router))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, step_handler))
app.add_handler(MessageHandler(filters.Document.ALL, file_handler))

print("🔥 BOT RUNNING")
app.run_polling()