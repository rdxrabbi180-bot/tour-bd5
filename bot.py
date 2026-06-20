# bot.py
# পুরো বট একটা ফাইলেই — config, database, bot logic সব এখানে
# কমান্ড: python bot.py
#
# চালানোর আগে নিচের BOT_TOKEN আর ADMIN_IDS বসিয়ে নিন (অথবা Environment Variable সেট করুন)

import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters, CallbackQueryHandler
)

# ============ CONFIG (এখানে আপনার তথ্য বসান) ============

# BotFather থেকে পাওয়া বট টোকেন। Environment Variable সেট থাকলে সেটাই ব্যবহার হবে,
# না থাকলে এখানে সরাসরি কোটের ভেতরে বসাতে পারেন।
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8644419315:AAEJw9-_Eiz9mQOfKYGI4Hl-LRJSDAyLpog")

# Admin-দের Telegram User ID। একাধিক admin চাইলে কমা দিয়ে আলাদা করুন।
_admin_ids_raw = os.environ.get("ADMIN_IDS", "8764998997")
ADMIN_IDS = [int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip()]

# পেমেন্ট নেওয়ার নাম্বার (bKash/Nagad) — এখানে নিজের নাম্বার বসান
PAYMENT_INFO = """
💳 Payment Info:
bKash (Send Money): 01XXXXXXXXX
Nagad (Send Money): 01XXXXXXXXX

পেমেন্ট করার পর Transaction ID (TrxID) বটে সাবমিট করুন।
"""

DB_NAME = "tournament.db"

# ============ লগিং ============

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ কথোপকথনের ধাপ (states) ============

(TEAM_NAME, P1_IGN, P1_UID, P2_IGN, P2_UID,
 P3_IGN, P3_UID, P4_IGN, P4_UID, TRX_ID) = range(10)

(T_NAME, T_FEE, T_SLOTS, T_TIME) = range(10, 14)

(ROOM_ID, ROOM_PASS) = range(20, 22)


def is_admin(user_id):
    return user_id in ADMIN_IDS


# ============ DATABASE ফাংশন ============

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            entry_fee INTEGER NOT NULL,
            max_slots INTEGER NOT NULL,
            match_time TEXT,
            status TEXT DEFAULT 'open',
            room_id TEXT,
            room_password TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            telegram_user_id INTEGER NOT NULL,
            telegram_username TEXT,
            team_name TEXT NOT NULL,
            player1_ign TEXT,
            player1_uid TEXT,
            player2_ign TEXT,
            player2_uid TEXT,
            player3_ign TEXT,
            player3_uid TEXT,
            player4_ign TEXT,
            player4_uid TEXT,
            trx_id TEXT,
            payment_status TEXT DEFAULT 'pending',
            slot_number INTEGER,
            FOREIGN KEY (tournament_id) REFERENCES tournaments (id)
        )
    """)

    conn.commit()
    conn.close()


def create_tournament(name, entry_fee, max_slots, match_time):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tournaments (name, entry_fee, max_slots, match_time) VALUES (?, ?, ?, ?)",
        (name, entry_fee, max_slots, match_time)
    )
    conn.commit()
    tournament_id = cur.lastrowid
    conn.close()
    return tournament_id


def get_open_tournaments():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tournaments WHERE status = 'open'")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_tournament(tournament_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,))
    row = cur.fetchone()
    conn.close()
    return row


def count_approved_slots(tournament_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) as cnt FROM registrations WHERE tournament_id = ? AND payment_status = 'approved'",
        (tournament_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row["cnt"]


def set_room_details(tournament_id, room_id, room_password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tournaments SET room_id = ?, room_password = ? WHERE id = ?",
        (room_id, room_password, tournament_id)
    )
    conn.commit()
    conn.close()


def create_registration(data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO registrations (
            tournament_id, telegram_user_id, telegram_username, team_name,
            player1_ign, player1_uid, player2_ign, player2_uid,
            player3_ign, player3_uid, player4_ign, player4_uid, trx_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["tournament_id"], data["telegram_user_id"], data["telegram_username"], data["team_name"],
        data["player1_ign"], data["player1_uid"], data["player2_ign"], data["player2_uid"],
        data["player3_ign"], data["player3_uid"], data["player4_ign"], data["player4_uid"], data["trx_id"]
    ))
    conn.commit()
    reg_id = cur.lastrowid
    conn.close()
    return reg_id


def get_registration(reg_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_pending_registrations():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM registrations WHERE payment_status = 'pending'")
    rows = cur.fetchall()
    conn.close()
    return rows


def approve_registration(reg_id, slot_number):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE registrations SET payment_status = 'approved', slot_number = ? WHERE id = ?",
        (slot_number, reg_id)
    )
    conn.commit()
    conn.close()


def reject_registration(reg_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE registrations SET payment_status = 'rejected' WHERE id = ?", (reg_id,))
    conn.commit()
    conn.close()


def get_approved_registrations(tournament_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM registrations WHERE tournament_id = ? AND payment_status = 'approved' ORDER BY slot_number",
        (tournament_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ============ ইউজার সাইড কমান্ড ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 স্বাগতম Free Fire Tournament Bot-এ!\n\n"
        "/tournaments - চলমান টুর্নামেন্ট দেখুন\n"
        "/cancel - চলমান কাজ বাতিল করুন"
    )


async def list_tournaments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tournaments = get_open_tournaments()
    if not tournaments:
        await update.message.reply_text("এই মুহূর্তে কোনো টুর্নামেন্ট ওপেন নেই। পরে চেক করুন।")
        return

    for t in tournaments:
        approved = count_approved_slots(t["id"])
        text = (
            f"🏆 {t['name']}\n"
            f"💰 Entry Fee: {t['entry_fee']} টাকা/স্কোয়াড\n"
            f"👥 স্লট: {approved}/{t['max_slots']}\n"
            f"🕒 ম্যাচ সময়: {t['match_time']}\n"
        )
        keyboard = None
        if approved < t["max_slots"]:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ রেজিস্টার করুন", callback_data=f"register_{t['id']}")]
            ])
        else:
            text += "\n❌ স্লট ফুল হয়ে গেছে।"
        await update.message.reply_text(text, reply_markup=keyboard)


# ============ রেজিস্ট্রেশন কথোপকথন ============

async def register_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tournament_id = int(query.data.split("_")[1])

    tournament = get_tournament(tournament_id)
    if not tournament or tournament["status"] != "open":
        await query.message.reply_text("দুঃখিত, এই টুর্নামেন্ট আর খোলা নেই।")
        return ConversationHandler.END

    approved = count_approved_slots(tournament_id)
    if approved >= tournament["max_slots"]:
        await query.message.reply_text("দুঃখিত, স্লট ফুল হয়ে গেছে।")
        return ConversationHandler.END

    context.user_data["tournament_id"] = tournament_id
    context.user_data["reg"] = {}

    await query.message.reply_text("আপনার টিমের নাম লিখুন:")
    return TEAM_NAME


async def get_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["team_name"] = update.message.text
    await update.message.reply_text("প্লেয়ার ১-এর IGN (in-game name) লিখুন:")
    return P1_IGN


async def get_p1_ign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player1_ign"] = update.message.text
    await update.message.reply_text("প্লেয়ার ১-এর UID লিখুন:")
    return P1_UID


async def get_p1_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player1_uid"] = update.message.text
    await update.message.reply_text("প্লেয়ার ২-এর IGN লিখুন:")
    return P2_IGN


async def get_p2_ign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player2_ign"] = update.message.text
    await update.message.reply_text("প্লেয়ার ২-এর UID লিখুন:")
    return P2_UID


async def get_p2_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player2_uid"] = update.message.text
    await update.message.reply_text("প্লেয়ার ৩-এর IGN লিখুন:")
    return P3_IGN


async def get_p3_ign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player3_ign"] = update.message.text
    await update.message.reply_text("প্লেয়ার ৩-এর UID লিখুন:")
    return P3_UID


async def get_p3_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player3_uid"] = update.message.text
    await update.message.reply_text("প্লেয়ার ৪-এর IGN লিখুন:")
    return P4_IGN


async def get_p4_ign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player4_ign"] = update.message.text
    await update.message.reply_text("প্লেয়ার ৪-এর UID লিখুন:")
    return P4_UID


async def get_p4_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["player4_uid"] = update.message.text

    tournament = get_tournament(context.user_data["tournament_id"])
    await update.message.reply_text(
        f"এখন পেমেন্ট করুন:\n{PAYMENT_INFO}\n"
        f"মোট দিতে হবে: {tournament['entry_fee']} টাকা\n\n"
        "পেমেন্ট করার পর Transaction ID (TrxID) এখানে লিখুন:"
    )
    return TRX_ID


async def get_trx_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg"]["trx_id"] = update.message.text

    reg_data = context.user_data["reg"]
    reg_data["tournament_id"] = context.user_data["tournament_id"]
    reg_data["telegram_user_id"] = update.effective_user.id
    reg_data["telegram_username"] = update.effective_user.username or update.effective_user.first_name

    reg_id = create_registration(reg_data)

    await update.message.reply_text(
        "✅ আপনার রেজিস্ট্রেশন জমা হয়েছে!\n"
        "Admin পেমেন্ট ভেরিফাই করার পর আপনাকে কনফার্মেশন পাঠানো হবে।\n"
        f"রেজিস্ট্রেশন ID: {reg_id}"
    )

    tournament = get_tournament(reg_data["tournament_id"])
    admin_text = (
        f"🆕 নতুন রেজিস্ট্রেশন (ID: {reg_id})\n"
        f"টুর্নামেন্ট: {tournament['name']}\n"
        f"টিম: {reg_data['team_name']}\n"
        f"Telegram: @{reg_data['telegram_username']}\n"
        f"TrxID: {reg_data['trx_id']}\n\n"
        f"Approve করতে: /approve {reg_id}\n"
        f"Reject করতে: /reject {reg_id}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception as e:
            logger.error(f"Admin {admin_id}-কে মেসেজ পাঠানো যায়নি: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("বাতিল করা হয়েছে।")
    return ConversationHandler.END


# ============ Admin: Approve/Reject ============

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার: /approve <registration_id>")
        return

    reg_id = int(context.args[0])
    reg = get_registration(reg_id)
    if not reg:
        await update.message.reply_text("রেজিস্ট্রেশন পাওয়া যায়নি।")
        return

    slot_number = count_approved_slots(reg["tournament_id"]) + 1
    approve_registration(reg_id, slot_number)

    await update.message.reply_text(f"✅ রেজিস্ট্রেশন {reg_id} approve করা হয়েছে। স্লট নম্বর: {slot_number}")

    try:
        await context.bot.send_message(
            chat_id=reg["telegram_user_id"],
            text=(
                f"🎉 আপনার পেমেন্ট কনফার্ম হয়েছে!\n"
                f"টিম: {reg['team_name']}\n"
                f"স্লট নম্বর: {slot_number}\n"
                "ম্যাচের আগে রুম আইডি/পাসওয়ার্ড পাঠানো হবে।"
            )
        )
    except Exception as e:
        logger.error(f"ইউজারকে মেসেজ পাঠানো যায়নি: {e}")


async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার: /reject <registration_id>")
        return

    reg_id = int(context.args[0])
    reg = get_registration(reg_id)
    if not reg:
        await update.message.reply_text("রেজিস্ট্রেশন পাওয়া যায়নি।")
        return

    reject_registration(reg_id)
    await update.message.reply_text(f"❌ রেজিস্ট্রেশন {reg_id} reject করা হয়েছে।")

    try:
        await context.bot.send_message(
            chat_id=reg["telegram_user_id"],
            text=f"❌ দুঃখিত, আপনার পেমেন্ট ভেরিফাই করা যায়নি (TrxID: {reg['trx_id']})। সঠিক তথ্য দিয়ে আবার চেষ্টা করুন বা admin-এর সাথে যোগাযোগ করুন।"
        )
    except Exception as e:
        logger.error(f"ইউজারকে মেসেজ পাঠানো যায়নি: {e}")


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    pending = get_pending_registrations()
    if not pending:
        await update.message.reply_text("কোনো pending রেজিস্ট্রেশন নেই।")
        return

    for reg in pending:
        text = (
            f"ID: {reg['id']} | টিম: {reg['team_name']}\n"
            f"Telegram: @{reg['telegram_username']}\n"
            f"TrxID: {reg['trx_id']}\n"
            f"/approve {reg['id']}  বা  /reject {reg['id']}"
        )
        await update.message.reply_text(text)


# ============ Admin: টুর্নামেন্ট তৈরি ============

async def newtournament_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text("টুর্নামেন্টের নাম লিখুন:")
    return T_NAME


async def new_t_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["t_name"] = update.message.text
    await update.message.reply_text("Entry fee কত (টাকায়, শুধু নাম্বার লিখুন)?")
    return T_FEE


async def new_t_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["t_fee"] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("সঠিক নাম্বার লিখুন:")
        return T_FEE
    await update.message.reply_text("সর্বোচ্চ কতগুলো স্কোয়াড স্লট থাকবে?")
    return T_SLOTS


async def new_t_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["t_slots"] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("সঠিক নাম্বার লিখুন:")
        return T_SLOTS
    await update.message.reply_text("ম্যাচের সময় লিখুন (যেমন: 21 জুন, রাত ৮টা):")
    return T_TIME


async def new_t_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match_time = update.message.text
    t_id = create_tournament(
        context.user_data["t_name"],
        context.user_data["t_fee"],
        context.user_data["t_slots"],
        match_time
    )
    await update.message.reply_text(f"✅ টুর্নামেন্ট তৈরি হয়েছে! ID: {t_id}")
    context.user_data.clear()
    return ConversationHandler.END


# ============ Admin: রুম আইডি সেট ও ব্রডকাস্ট ============

async def setroom_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text("ব্যবহার: /setroom <tournament_id>")
        return ConversationHandler.END

    context.user_data["room_tournament_id"] = int(context.args[0])
    await update.message.reply_text("Room ID লিখুন:")
    return ROOM_ID


async def setroom_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["room_id"] = update.message.text
    await update.message.reply_text("Room Password লিখুন:")
    return ROOM_PASS


async def setroom_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    room_password = update.message.text
    tournament_id = context.user_data["room_tournament_id"]
    room_id = context.user_data["room_id"]

    set_room_details(tournament_id, room_id, room_password)
    tournament = get_tournament(tournament_id)
    approved_regs = get_approved_registrations(tournament_id)

    broadcast_text = (
        f"🎮 {tournament['name']} - Room Details\n"
        f"Room ID: {room_id}\n"
        f"Password: {room_password}\n\n"
        "সঠিক সময়ে জয়েন করুন। গুড লাক! 🔥"
    )

    sent = 0
    for reg in approved_regs:
        try:
            await context.bot.send_message(chat_id=reg["telegram_user_id"], text=broadcast_text)
            sent += 1
        except Exception as e:
            logger.error(f"User {reg['telegram_user_id']}-কে রুম আইডি পাঠানো যায়নি: {e}")

    await update.message.reply_text(f"✅ রুম আইডি/পাসওয়ার্ড {sent} জন approved player-কে পাঠানো হয়েছে।")
    context.user_data.clear()
    return ConversationHandler.END


# ============ মেইন ফাংশন ============

def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tournaments", list_tournaments))

    registration_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(register_button, pattern=r"^register_\d+$")],
        states={
            TEAM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_team_name)],
            P1_IGN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p1_ign)],
            P1_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p1_uid)],
            P2_IGN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p2_ign)],
            P2_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p2_uid)],
            P3_IGN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p3_ign)],
            P3_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p3_uid)],
            P4_IGN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p4_ign)],
            P4_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_p4_uid)],
            TRX_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_trx_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(registration_conv)

    newtournament_conv = ConversationHandler(
        entry_points=[CommandHandler("newtournament", newtournament_start)],
        states={
            T_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_t_name)],
            T_FEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_t_fee)],
            T_SLOTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_t_slots)],
            T_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_t_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(newtournament_conv)

    setroom_conv = ConversationHandler(
        entry_points=[CommandHandler("setroom", setroom_start)],
        states={
            ROOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, setroom_id)],
            ROOM_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, setroom_pass)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(setroom_conv)

    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reject", reject_cmd))
    app.add_handler(CommandHandler("pending", pending_cmd))

    print("বট চালু হয়েছে... (বন্ধ করতে Ctrl+C চাপুন)")
    app.run_polling()


if __name__ == "__main__":
    main()
