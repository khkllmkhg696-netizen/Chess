#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت شطرنج تيليجرام - Chess Telegram Bot
يتطلب: pip install python-telegram-bot flask

الإعداد:
1. شغّل الملف: python chess_bot.py
2. اضبط متغيرات البيئة:
   export BOT_TOKEN=توكن_البوت
   export WEBAPP_URL=https://yourname.replit.app
   export BOT_USERNAME=اسم_البوت_بدون_@
3. فعّل الـ Inline Mode في @BotFather
4. لـ UptimeRobot: استخدم رابط / أو /ping
"""

import os
import threading
import uuid
import time
import copy
import asyncio
import logging

from flask import Flask, request, jsonify, render_template_string
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, InlineQueryResultArticle, InputTextMessageContent,
    SwitchInlineQueryChosenChat
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    InlineQueryHandler, ContextTypes
)

# ============================================================
#  الإعدادات
# ============================================================
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "8693975581:AAGGEbsizrkMss9tLEcA1Z1b2j6Eh92zlus")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "shetrnj_bot")
WEBAPP_URL   = os.environ.get("WEBAPP_URL", "https://chess-d12v.onrender.com")
PORT         = int(os.environ.get("PORT", 8080))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================
#  إدارة حالة الألعاب في الذاكرة
# ============================================================
games: dict = {}


def new_board():
    return [
        ["bR","bN","bB","bQ","bK","bB","bN","bR"],
        ["bP","bP","bP","bP","bP","bP","bP","bP"],
        [None]*8, [None]*8, [None]*8, [None]*8,
        ["wP","wP","wP","wP","wP","wP","wP","wP"],
        ["wR","wN","wB","wQ","wK","wB","wN","wR"],
    ]


def create_game(creator_id: str, creator_name: str) -> str:
    gid = str(uuid.uuid4())[:8].upper()
    games[gid] = {
        "id":         gid,
        "board":      new_board(),
        "turn":       "w",
        "status":     "waiting",
        "players":    {"w": creator_id, "b": None},
        "names":      {"w": creator_name, "b": "؟"},
        "en_passant": None,
        "winner":     None,
        "created":    time.time(),
        "move_time":  None,
        "timers":     {"w": 60.0, "b": 60.0},
    }
    return gid


# ============================================================
#  منطق حركات الشطرنج
# ============================================================

def _raw_moves(board, r, c, ep=None):
    p = board[r][c]
    if not p:
        return []
    col, pt = p[0], p[1]
    opp = "b" if col == "w" else "w"
    res = []

    def ok(nr, nc):
        return (0 <= nr <= 7 and 0 <= nc <= 7
                and (not board[nr][nc] or board[nr][nc][0] == opp))

    def slide(dr, dc):
        nr, nc = r + dr, c + dc
        while 0 <= nr <= 7 and 0 <= nc <= 7:
            if board[nr][nc]:
                if board[nr][nc][0] == opp:
                    res.append((nr, nc))
                break
            res.append((nr, nc))
            nr += dr; nc += dc

    if pt == "P":
        d  = -1 if col == "w" else 1
        sr =  6 if col == "w" else 1
        if 0 <= r+d <= 7 and not board[r+d][c]:
            res.append((r+d, c))
            if r == sr and not board[r+2*d][c]:
                res.append((r+2*d, c))
        for dc in [-1, 1]:
            nr, nc = r+d, c+dc
            if 0 <= nr <= 7 and 0 <= nc <= 7:
                if board[nr][nc] and board[nr][nc][0] == opp:
                    res.append((nr, nc))
                elif ep and ep == [nr, nc]:
                    res.append((nr, nc))
    elif pt == "R":
        slide(1,0); slide(-1,0); slide(0,1); slide(0,-1)
    elif pt == "N":
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            if ok(r+dr, c+dc):
                res.append((r+dr, c+dc))
    elif pt == "B":
        slide(1,1); slide(1,-1); slide(-1,1); slide(-1,-1)
    elif pt == "Q":
        slide(1,0); slide(-1,0); slide(0,1); slide(0,-1)
        slide(1,1); slide(1,-1); slide(-1,1); slide(-1,-1)
    elif pt == "K":
        for dr, dc in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            if ok(r+dr, c+dc):
                res.append((r+dr, c+dc))
    return res


def _in_check(board, col):
    king_pos = None
    for r in range(8):
        for c in range(8):
            if board[r][c] == col + "K":
                king_pos = (r, c)
                break
    if not king_pos:
        return False
    opp = "b" if col == "w" else "w"
    for r in range(8):
        for c in range(8):
            if board[r][c] and board[r][c][0] == opp:
                if king_pos in _raw_moves(board, r, c):
                    return True
    return False


def legal_moves(board, r, c, ep=None):
    p = board[r][c]
    if not p:
        return []
    col = p[0]
    result = []
    for (nr, nc) in _raw_moves(board, r, c, ep):
        b2 = copy.deepcopy(board)
        if p[1] == "P" and ep and ep == [nr, nc]:
            b2[r][nc] = None
        b2[nr][nc] = p
        b2[r][c]  = None
        if not _in_check(b2, col):
            result.append((nr, nc))
    return result


def _has_any_moves(board, col, ep=None):
    for r in range(8):
        for c in range(8):
            if board[r][c] and board[r][c][0] == col:
                if legal_moves(board, r, c, ep):
                    return True
    return False


def apply_move(game, fr, fc, tr, tc):
    board = game["board"]
    p     = board[fr][fc]
    if not p:
        return "لا توجد قطعة في هذا الموقع"

    col, pt = p[0], p[1]
    opp     = "b" if col == "w" else "w"
    ep      = game.get("en_passant")

    if col != game["turn"]:
        return "ليس دورك"

    if (tr, tc) not in legal_moves(board, fr, fc, ep):
        return "حركة غير مسموح بها"

    nb     = copy.deepcopy(board)
    new_ep = None

    if pt == "P":
        if ep and ep == [tr, tc]:
            nb[fr][tc] = None
        if abs(tr - fr) == 2:
            new_ep = [(fr + tr) // 2, fc]
        nb[tr][tc] = col + "Q" if tr in (0, 7) else p
    else:
        nb[tr][tc] = p
    nb[fr][fc] = None

    game["board"]      = nb
    game["en_passant"] = new_ep
    game["turn"]       = opp
    game["move_time"]  = time.time()

    if not _has_any_moves(nb, opp, new_ep):
        if _in_check(nb, opp):
            game["status"] = "checkmate"
            game["winner"] = col
        else:
            game["status"] = "stalemate"
    elif _in_check(nb, opp):
        game["status"] = "check"
    else:
        game["status"] = "playing"

    return None


# ============================================================
#  HTML لعبة الشطرنج (Mini App)
# ============================================================

CHESS_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>شطرنج</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{
  background:#1a1a2e;
  color:#fff;
  font-family:Arial,Helvetica,sans-serif;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  padding:6px;
  height:100vh;
}
.player-row{
  width:100%;
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:5px 12px;
  background:rgba(255,255,255,0.08);
  border-radius:10px;
  margin:3px 0;
}
.p-name{font-size:13px;font-weight:bold;max-width:180px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.p-timer{font-size:18px;font-weight:bold;font-family:monospace;color:#f0c040;min-width:55px;text-align:left}
.p-timer.active{color:#4fffc4}
#status{
  width:100%;
  text-align:center;
  padding:6px;
  font-size:13px;
  background:rgba(255,255,255,0.08);
  border-radius:8px;
  margin:3px 0;
  min-height:32px;
  transition:background .3s
}
#status.my-turn{background:rgba(79,255,196,0.18);color:#4fffc4}
#status.waiting{color:#f0c040}
#status.gameover{background:rgba(255,107,107,0.18);color:#ff6b6b}
#board-wrap{margin:4px 0}
#board{
  display:grid;
  grid-template-columns:repeat(8,1fr);
  border:2px solid #555;
  border-radius:3px;
  overflow:hidden;
}
.cell{
  width:calc(min(100vw,100vh - 160px)/8);
  height:calc(min(100vw,100vh - 160px)/8);
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;
  position:relative;
  font-size:calc(min(100vw,100vh - 160px)/8*.72);
  user-select:none;-webkit-user-select:none;
  transition:background .1s;
  touch-action:manipulation;
}
.cell.light{background:#f0d9b5}
.cell.dark{background:#b58863}
.cell.selected{background:#f6f669!important}
.cell.last-from,.cell.last-to{background:#cdd16e!important}
.dot{
  position:absolute;
  width:33%;height:33%;
  background:rgba(0,0,0,0.25);
  border-radius:50%;
  pointer-events:none;z-index:2
}
.ring{
  position:absolute;inset:0;
  border:4px solid rgba(0,0,0,0.25);
  border-radius:50%;
  pointer-events:none;z-index:2
}
.piece{position:relative;z-index:1;line-height:1}
</style>
</head>
<body>

<div class="player-row" id="row-opp">
  <span class="p-name" id="opp-name">اللاعب الثاني</span>
  <span class="p-timer" id="opp-timer">01:00</span>
</div>

<div id="status" class="waiting">⏳ جاري التحميل…</div>

<div id="board-wrap">
  <div id="board"></div>
</div>

<div class="player-row" id="row-me">
  <span class="p-name" id="me-name">أنت</span>
  <span class="p-timer" id="me-timer">01:00</span>
</div>

<script>
const tg = window.Telegram.WebApp;
tg.ready(); tg.expand();

const params   = new URLSearchParams(location.search);
const gameId   = params.get("game_id") || "";
const myId     = String(params.get("player_id") || tg?.initDataUnsafe?.user?.id || "");
const myName   = params.get("player_name") || tg?.initDataUnsafe?.user?.first_name || "أنت";

const PIECES = {
  wK:"♔",wQ:"♕",wR:"♖",wB:"♗",wN:"♘",wP:"♙",
  bK:"♚",bQ:"♛",bR:"♜",bB:"♝",bN:"♞",bP:"♟"
};

let state    = null;
let myColor  = null;
let selR = -1, selC = -1;
let movable  = [];
let lastFrom = null, lastTo = null;

async function poll() {
  try {
    const r = await fetch(
      `/api/game/${gameId}?player_id=${encodeURIComponent(myId)}&player_name=${encodeURIComponent(myName)}`
    );
    const d = await r.json();
    if (d.error) { setStatus(d.error, ""); return; }

    const changed = !state
      || JSON.stringify(d.board) !== JSON.stringify(state?.board)
      || d.status !== state?.status
      || d.players.b !== state?.players?.b;

    state = d;

    if (!myColor) {
      if (d.players.w === myId) myColor = "w";
      else if (d.players.b === myId) myColor = "b";
    }

    if (changed) {
      selR = -1; selC = -1; movable = [];
      render();
    }
    updateStatus();
    updateTimers();
  } catch(e) {}
}

function render() {
  if (!state) return;
  const el   = document.getElementById("board");
  el.innerHTML = "";
  const flip = myColor === "b";

  for (let ri = 0; ri < 8; ri++) {
    for (let ci = 0; ci < 8; ci++) {
      const r = flip ? 7-ri : ri;
      const c = flip ? 7-ci : ci;
      const piece = state.board[r][c];
      const light = (r+c) % 2 === 0;

      const div = document.createElement("div");
      div.className = "cell " + (light ? "light" : "dark");
      div.dataset.r = r; div.dataset.c = c;

      if (r === selR && c === selC) div.classList.add("selected");
      if (lastFrom && lastFrom[0]===r && lastFrom[1]===c) div.classList.add("last-from");
      if (lastTo   && lastTo[0]===r   && lastTo[1]===c)   div.classList.add("last-to");

      const isMove = movable.some(m => m[0]===r && m[1]===c);
      if (isMove) {
        const mark = document.createElement("div");
        mark.className = piece ? "ring" : "dot";
        div.appendChild(mark);
      }

      if (piece) {
        const sp = document.createElement("span");
        sp.className   = "piece";
        sp.textContent = PIECES[piece] || "";
        div.appendChild(sp);
      }

      div.addEventListener("click", onClick);
      el.appendChild(div);
    }
  }

  const oppColor = myColor === "w" ? "b" : "w";
  document.getElementById("me-name").textContent  = state.names[myColor  || "w"] || "أنت";
  document.getElementById("opp-name").textContent = state.names[oppColor || "b"] || "اللاعب الثاني";
}

function onClick(e) {
  const div = e.currentTarget;
  const r   = parseInt(div.dataset.r);
  const c   = parseInt(div.dataset.c);

  if (!state || !myColor) return;
  const active = state.status === "playing" || state.status === "check";
  if (!active || state.turn !== myColor) return;

  if (selR >= 0 && movable.some(m => m[0]===r && m[1]===c)) {
    doMove(selR, selC, r, c);
    return;
  }

  const piece = state.board[r][c];
  if (piece && piece[0] === myColor) {
    selR = r; selC = c;
    fetch(`/api/game/${gameId}/moves?r=${r}&c=${c}`)
      .then(x => x.json())
      .then(d => { movable = d.moves || []; render(); });
  } else {
    selR = -1; selC = -1; movable = [];
    render();
  }
}

async function doMove(fr, fc, tr, tc) {
  selR = -1; selC = -1; movable = [];
  try {
    const res = await fetch(`/api/game/${gameId}/move`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({player_id: myId, from:[fr,fc], to:[tr,tc]})
    });
    const d = await res.json();
    if (d.error) { alert(d.error); return; }
    lastFrom = [fr, fc]; lastTo = [tr, tc];
    state = d;
    render(); updateStatus(); updateTimers();
  } catch(e) {}
}

function setStatus(txt, cls) {
  const el = document.getElementById("status");
  el.textContent = txt; el.className = cls || "";
}

function updateStatus() {
  if (!state) return;
  const s = state.status;
  if (s === "waiting") {
    setStatus("⏳ في انتظار انضمام الخصم…", "waiting");
  } else if (s === "playing" || s === "check") {
    if (state.turn === myColor) {
      setStatus(s === "check" ? "⚠️ ملكك في خطر! دورك للعب" : "🎯 دورك! اختر قطعة", "my-turn");
    } else {
      setStatus(s === "check" ? "⚠️ الخصم في خطر! دور الخصم" : "⏳ دور الخصم…", "");
    }
  } else if (s === "checkmate") {
    setStatus(state.winner === myColor ? "🏆 فزت! كش مات!" : "😔 خسرت! كش مات.", "gameover");
  } else if (s === "stalemate") {
    setStatus("🤝 تعادل! لا توجد حركات ممكنة.", "gameover");
  }
}

function fmt(s) {
  const m  = Math.floor(Math.max(0,s)/60);
  const sc = Math.floor(Math.max(0,s) % 60);
  return String(m).padStart(2,"0") + ":" + String(sc).padStart(2,"0");
}

function updateTimers() {
  if (!state) return;
  const opp = myColor === "w" ? "b" : "w";
  document.getElementById("me-timer").textContent  = fmt(state.timers[myColor || "w"]);
  document.getElementById("opp-timer").textContent = fmt(state.timers[opp    || "b"]);

  const mEl  = document.getElementById("me-timer");
  const opEl = document.getElementById("opp-timer");
  const active = state.status === "playing" || state.status === "check";
  if (active && state.turn === myColor) {
    mEl.classList.add("active"); opEl.classList.remove("active");
  } else {
    opEl.classList.add("active"); mEl.classList.remove("active");
  }
}

poll();
setInterval(poll, 1500);
</script>
</body>
</html>"""


# ============================================================
#  Flask Web Server
# ============================================================
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return jsonify({"status": "ok", "message": "بوت الشطرنج يعمل! ♟️"})


@flask_app.route("/ping")
def ping():
    return "OK", 200


@flask_app.route("/health")
def health():
    return jsonify({"status": "healthy", "games": len(games)})


@flask_app.route("/chess")
def chess_page():
    return render_template_string(CHESS_HTML)


@flask_app.route("/api/game/<gid>")
def api_get_game(gid):
    if gid not in games:
        return jsonify({"error": "لعبة غير موجودة"}), 404

    game  = games[gid]
    pid   = request.args.get("player_id", "")
    pname = request.args.get("player_name", "لاعب")

    if pid and game["status"] == "waiting":
        if pid != game["players"]["w"] and not game["players"]["b"]:
            game["players"]["b"] = pid
            game["names"]["b"]   = pname
            game["status"]       = "playing"
            game["move_time"]    = time.time()

    return jsonify(game)


@flask_app.route("/api/game/<gid>/moves")
def api_get_moves(gid):
    if gid not in games:
        return jsonify({"moves": []})
    game = games[gid]
    try:
        r = int(request.args.get("r", -1))
        c = int(request.args.get("c", -1))
    except Exception:
        return jsonify({"moves": []})
    if r < 0 or c < 0:
        return jsonify({"moves": []})
    moves = legal_moves(game["board"], r, c, game.get("en_passant"))
    return jsonify({"moves": [list(m) for m in moves]})


@flask_app.route("/api/game/<gid>/move", methods=["POST"])
def api_make_move(gid):
    if gid not in games:
        return jsonify({"error": "لعبة غير موجودة"}), 404
    game = games[gid]
    data = request.json or {}
    pid  = str(data.get("player_id", ""))
    frm  = data.get("from")
    to   = data.get("to")

    if not frm or not to or len(frm) != 2 or len(to) != 2:
        return jsonify({"error": "بيانات ناقصة"}), 400

    turn_color = game["turn"]
    expected   = game["players"]["w"] if turn_color == "w" else game["players"]["b"]
    if pid != str(expected):
        return jsonify({"error": "ليس دورك"}), 403

    if game["status"] not in ("playing", "check"):
        return jsonify({"error": "اللعبة لم تبدأ أو انتهت"}), 400

    err = apply_move(game, frm[0], frm[1], to[0], to[1])
    if err:
        return jsonify({"error": err}), 400

    return jsonify(game)


# ============================================================
#  معالجات بوت تيليجرام
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    معالجة /start
    - إذا جاء مع باراميتر (مثل /start GAMEID) يعني شخص ضغط زر الدعوة،
      فيُفتح له رسالة مع زر WebApp يحمل هويته الخاصة.
    - بدون باراميتر: رسالة ترحيب عادية.
    """
    user = update.effective_user
    args = context.args

    if args:
        gid = args[0].upper()

        if gid not in games:
            await update.message.reply_text(
                "⚠️ انتهت صلاحية هذه الدعوة أو أن اللعبة لم تعد موجودة.\n\n"
                "يمكنك إنشاء لعبة جديدة بالضغط على /start",
            )
            return

        game = games[gid]

        if game["players"]["b"] and game["players"]["b"] != str(user.id):
            await update.message.reply_text(
                "⚠️ اللعبة ممتلئة بالفعل!\n\n"
                "اضغط /start لإنشاء لعبة جديدة."
            )
            return

        game_url = (
            f"{WEBAPP_URL}/chess"
            f"?game_id={gid}"
            f"&player_id={user.id}"
            f"&player_name={user.first_name}"
        )

        creator_name = game["names"]["w"]
        kb = [[
            InlineKeyboardButton(
                "♟️ ادخل اللعبة الآن",
                web_app=WebAppInfo(url=game_url),
            )
        ]]
        await update.message.reply_text(
            f"♟️ *دعوة شطرنج!*\n\n"
            f"👤 *{creator_name}* يدعوك للعب شطرنج\n"
            f"⏱ الوقت: دقيقة لكل لاعب\n"
            f"🎲 الألوان: عشوائية\n\n"
            f"اضغط الزر أدناه للدخول مباشرة! 👇",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown",
        )
        return

    kb = [[InlineKeyboardButton("🎮 العب مع صديق", callback_data="new_game")]]
    await update.message.reply_text(
        "♟️ *أهلاً وسهلاً في بوت الشطرنج!*\n\n"
        "تحدَّ أصدقاءك في لعبة شطرنج مباشرة عبر تيليجرام!\n\n"
        "📌 *طريقة اللعب:*\n"
        "١ ─ اضغط «العب مع صديق»\n"
        "٢ ─ اختر الشخص أو المجموعة التي تريد دعوتها\n"
        "٣ ─ يصله رابط الدعوة، يضغطه ويدخل اللعبة مباشرة!\n\n"
        "🏆 القطعة البيضاء تبدأ أولاً\n"
        "⏱ وقت كل لاعب: دقيقة واحدة",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغط الأزرار"""
    q = update.callback_query
    await q.answer()

    if q.data in ("new_game", "play_again"):
        user = q.from_user
        gid  = create_game(str(user.id), user.first_name)

        kb = [[
            InlineKeyboardButton(
                "📨 شارك الدعوة مع صديق",
                switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
                    query=gid,
                    allow_user_chats=True,
                    allow_bot_chats=False,
                    allow_group_chats=True,
                    allow_channel_chats=False,
                ),
            )
        ], [
            InlineKeyboardButton(
                "▶️ افتح لعبتي أنا",
                web_app=WebAppInfo(
                    url=f"{WEBAPP_URL}/chess?game_id={gid}&player_id={user.id}&player_name={user.first_name}"
                ),
            )
        ]]

        label = "🔄 *لعبة جديدة!*" if q.data == "play_again" else "🎮 *تم إنشاء لعبة جديدة!*"
        await q.message.reply_text(
            f"{label}\n\n"
            f"👤 المنشئ: {user.first_name}\n"
            f"⏱ الوقت: دقيقة لكل لاعب\n\n"
            f"📩 اضغط «شارك الدعوة» لإرسالها لصديقك،\n"
            f"أو افتح لعبتك أنت وانتظره!",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown",
        )


async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    معالجة الـ Inline Query.
    ترسل رسالة دعوة مع زر URL يوجّه المدعو للبوت برابط start=GAMEID
    بحيث البوت يفتح WebApp بهوية المدعو الصحيحة.
    """
    query = update.inline_query
    gid   = (query.query or "").strip().upper()

    if not gid or gid not in games:
        user = query.from_user
        gid  = create_game(str(user.id), user.first_name)

    user = query.from_user
    invite_link = f"https://t.me/{BOT_USERNAME}?start={gid}"

    result = InlineQueryResultArticle(
        id=gid,
        title="♟️ دعوة لعب شطرنج",
        description="انقر لإرسال دعوة شطرنج إلى هذه المحادثة!",
        input_message_content=InputTextMessageContent(
            message_text=(
                f"♟️ *{user.first_name}* يتحداك بالشطرنج\\!\n\n"
                f"⏱ الوقت: دقيقة لكل لاعب\n"
                f"🎲 الألوان: عشوائية\n\n"
                f"اضغط الزر أدناه للانضمام مباشرة\\! 👇"
            ),
            parse_mode="MarkdownV2",
        ),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "♟️ انضم للعبة الآن",
                url=invite_link,
            )
        ]]),
    )

    await query.answer(
        results=[result],
        cache_time=0,
        is_personal=True,
    )


# ============================================================
#  تشغيل Flask في خيط منفصل
# ============================================================

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ============================================================
#  تشغيل البوت
# ============================================================

async def bot_main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(InlineQueryHandler(inline_handler))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("✅ البوت يعمل الآن!")
    await asyncio.Event().wait()


# ============================================================
#  النقطة الرئيسية
# ============================================================

if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info(f"🌐 خادم الويب يعمل على المنفذ {PORT}")

    try:
        asyncio.run(bot_main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف البوت...")
