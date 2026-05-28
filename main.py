import os
import json
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine
from datetime import datetime

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

app = FastAPI()

DB_FILE = "data.json"

# =========================================================
# LOAD DATABASE
# Reads data.json, rehydrates daily_ranges into engine memory,
# and computes all analytics stats fresh from history.
# =========================================================

def load_data():

    if os.path.exists(DB_FILE):

        try:

            with open(DB_FILE, "r") as f:
                db = json.load(f)

            if "active" not in db:
                db["active"] = []

            if "history" not in db:
                db["history"] = []

            if "daily_ranges" not in db:
                db["daily_ranges"] = {}

            # Rehydrate engine's in-memory daily_ranges from disk
            # so breakout state survives server restarts.
            engine.daily_ranges.clear()
            engine.daily_ranges.update(db["daily_ranges"])

            # =================================================
            # ADVANCED STATS ENGINE
            # =================================================

            stats = {

                "wins": 0,
                "losses": 0,
                "total": 0,

                "rr_won": 0.0,
                "rr_lost": 0.0,
                "net_rr": 0.0,

                "profit_factor": 0.0,
                "expectancy": 0.0,

                "pairs": {},
                "strategies": {}
            }

            # =================================================
            # PROCESS HISTORY
            # =================================================

            for s in db.get("history", []):

                symbol = s.get("symbol", "UNKNOWN")

                strategy = s.get("strat", "UNKNOWN")

                rr_text = str(s.get("rr", "1:1"))

                stats["total"] += 1

                # -----------------------------------------
                # EXTRACT RR VALUE
                # -----------------------------------------

                try:

                    rr_value = float(rr_text.split(":")[1])

                except (ValueError, IndexError):

                    rr_value = 1.0

                # -----------------------------------------
                # PAIR STATS
                # -----------------------------------------

                if symbol not in stats["pairs"]:

                    stats["pairs"][symbol] = {

                        "wins": 0,
                        "losses": 0,
                        "total": 0,
                        "rr": 0.0
                    }

                stats["pairs"][symbol]["total"] += 1

                # -----------------------------------------
                # STRATEGY STATS
                # -----------------------------------------

                if strategy not in stats["strategies"]:

                    stats["strategies"][strategy] = {

                        "wins": 0,
                        "losses": 0,
                        "total": 0
                    }

                stats["strategies"][strategy]["total"] += 1

                # -----------------------------------------
                # WINS
                # -----------------------------------------

                if s.get("result") == "WIN":

                    stats["wins"] += 1

                    stats["rr_won"] += rr_value

                    stats["pairs"][symbol]["wins"] += 1

                    stats["pairs"][symbol]["rr"] += rr_value

                    stats["strategies"][strategy]["wins"] += 1

                # -----------------------------------------
                # LOSSES
                # -----------------------------------------

                elif s.get("result") == "LOSS":

                    stats["losses"] += 1

                    stats["rr_lost"] += 1.0

                    stats["pairs"][symbol]["losses"] += 1

                    stats["pairs"][symbol]["rr"] -= 1.0

                    stats["strategies"][strategy]["losses"] += 1

            # =================================================
            # FINAL METRICS
            # =================================================

            stats["net_rr"] = round(
                stats["rr_won"] - stats["rr_lost"],
                2
            )

            if stats["rr_lost"] > 0:

                stats["profit_factor"] = round(
                    stats["rr_won"] / stats["rr_lost"],
                    2
                )

            else:

                stats["profit_factor"] = round(
                    stats["rr_won"],
                    2
                )

            if stats["total"] > 0:

                stats["expectancy"] = round(
                    stats["net_rr"] / stats["total"],
                    2
                )

            db["stats"] = stats

            return db

        except Exception as e:

            logging.error(f"Database load error: {e}")

    # =========================================================
    # EMPTY DATABASE — returned on first run or corrupt file
    # =========================================================

    return {

        "active": [],
        "history": [],
        "daily_ranges": {},

        "stats": {

            "wins": 0,
            "losses": 0,
            "total": 0,

            "rr_won": 0.0,
            "rr_lost": 0.0,
            "net_rr": 0.0,

            "profit_factor": 0.0,
            "expectancy": 0.0,

            "pairs": {},
            "strategies": {}
        }
    }

# =========================================================
# SAVE DATABASE
# Saves active trades, history, and daily_ranges to disk.
# The computed stats dict is NOT saved — it is always
# recalculated fresh from history on load.
# =========================================================

def save_data(data):

    to_save = {

        "active": data.get("active", []),

        "history": data.get("history", []),

        # Persist breakout state so it survives restarts.
        "daily_ranges": engine.daily_ranges
    }

    with open(DB_FILE, "w") as f:

        json.dump(to_save, f, indent=2)

# =========================================================
# ACTIVE TRADE MONITOR
# Checks every active trade against the latest candle
# and closes it as WIN or LOSS if TP/SL was hit.
# =========================================================

def evaluate_active_trades(db):

    still_active = []

    for trade in db.get("active", []):

        symbol = trade.get("symbol")

        interval = (
            "5min"
            if trade.get("strat") == "Hybrid Fake Breakout"
            else "1day"
        )

        try:

            df = engine.get_data(
                symbol,
                interval,
                outputsize=2
            )

            if df is None or df.empty:

                still_active.append(trade)

                continue

            last_candle = df.iloc[-1]

            high = float(last_candle["high"])

            low = float(last_candle["low"])

            tp = float(trade.get("tp", 0))

            sl = float(trade.get("sl", 0))

            trade_type = trade.get("type")

            was_hit = False

            result = None

            # =============================================
            # BUY TRADE EVALUATION
            # =============================================

            if trade_type == "BUY":

                if high >= tp:

                    was_hit = True

                    result = "WIN"

                elif low <= sl:

                    was_hit = True

                    result = "LOSS"

            # =============================================
            # SELL TRADE EVALUATION
            # =============================================

            elif trade_type == "SELL":

                if low <= tp:

                    was_hit = True

                    result = "WIN"

                elif high >= sl:

                    was_hit = True

                    result = "LOSS"

            # =============================================
            # CLOSE TRADE
            # =============================================

            if was_hit:

                trade["result"] = result

                trade["closed_at"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                db["history"].insert(0, trade)

                logging.info(
                    f"Trade Closed: {symbol} | {trade_type} | {result}"
                )

            else:

                still_active.append(trade)

        except Exception as e:

            logging.error(
                f"Error evaluating active trade [{symbol}]: {e}"
            )

            still_active.append(trade)

    db["active"] = still_active

    return db

# =========================================================
# DASHBOARD
# =========================================================

@app.get("/", response_class=HTMLResponse)
def dashboard():

    db = load_data()

    try:

        with open("index.html", "r") as f:

            template = f.read()

    except FileNotFoundError:

        return HTMLResponse(
            content="<h2>index.html not found</h2>",
            status_code=500
        )

    stats = db["stats"]

    # =====================================================
    # HISTORY TABLE ROWS
    # =====================================================

    history_rows = ""

    for s in db.get("history", [])[:20]:

        type_color = (
            "#00ff99"
            if s.get("type") == "BUY"
            else "#ff3b6b"
        )

        result_color = (
            "#00ff99"
            if s.get("result") == "WIN"
            else "#ff3b6b"
        )

        history_rows += (
            f"<tr>"
            f"<td>{s.get('symbol', '-')}</td>"
            f"<td style='color:{type_color};font-weight:700'>"
            f"{s.get('type', '-')}</td>"
            f"<td>{s.get('entry', '-')}</td>"
            f"<td>{s.get('sl', '-')}</td>"
            f"<td>{s.get('tp', '-')}</td>"
            f"<td>{s.get('rr', '-')}</td>"
            f"<td style='color:{result_color};font-weight:700'>"
            f"{s.get('result', '-')}</td>"
            f"</tr>"
        )

    # =====================================================
    # ACTIVE TABLE ROWS
    # =====================================================

    active_rows = ""

    for s in db.get("active", []):

        type_color = (
            "#00ff99"
            if s.get("type") == "BUY"
            else "#ff3b6b"
        )

        active_rows += (
            f"<tr>"
            f"<td>{s.get('symbol', '-')}</td>"
            f"<td style='color:{type_color};font-weight:700'>"
            f"{s.get('type', '-')}</td>"
            f"<td>{s.get('entry', '-')}</td>"
            f"<td>{s.get('sl', '-')}</td>"
            f"<td>{s.get('tp', '-')}</td>"
            f"<td>{s.get('rr', '-')}</td>"
            f"<td style='color:#38bdf8;font-weight:700'>"
            f"ACTIVE</td>"
            f"</tr>"
        )

    # =====================================================
    # PAIR STATS CARDS
    # =====================================================

    pair_html = ""

    for pair, p_data in stats["pairs"].items():

        wr = (
            (p_data["wins"] / p_data["total"]) * 100
            if p_data["total"] > 0
            else 0
        )

        pair_html += (
            f"<div class='pair-card'>"
            f"<div class='p-name'>{pair}</div>"
            f"<div class='p-wr'>{wr:.1f}%</div>"
            f"<div class='p-count'>{p_data['total']} Signals</div>"
            f"<div class='p-count'>RR: {round(p_data['rr'], 2)}</div>"
            f"</div>"
        )

    # =====================================================
    # STRATEGY STATS ROWS
    # =====================================================

    strategy_html = ""

    for strat_name, s_data in stats["strategies"].items():

        s_wr = (
            (s_data["wins"] / s_data["total"]) * 100
            if s_data["total"] > 0
            else 0
        )

        strategy_html += (
            f"<tr>"
            f"<td>{strat_name}</td>"
            f"<td>{s_data['total']}</td>"
            f"<td style='color:#00ff99'>{s_data['wins']}</td>"
            f"<td style='color:#ff3b6b'>{s_data['losses']}</td>"
            f"<td>{s_wr:.1f}%</td>"
            f"</tr>"
        )

    # =====================================================
    # GLOBAL WIN RATE
    # =====================================================

    global_wr = (
        (stats["wins"] / stats["total"]) * 100
        if stats["total"] > 0
        else 0
    )

    last_scan = datetime.now().strftime("%Y-%m-%
            
