import os
import json
import logging
import uvicorn

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

import engine

from datetime import datetime

# =========================================================
# FASTAPI
# =========================================================

app = FastAPI()

# =========================================================
# DATABASE FILE
# =========================================================

DB_FILE = "data.json"

# =========================================================
# LOAD DATABASE
# =========================================================

def load_data():

    if os.path.exists(DB_FILE):

        try:

            with open(DB_FILE, "r") as f:

                db = json.load(f)

            # =============================================
            # SAFETY DEFAULTS
            # =============================================

            if "active" not in db:
                db["active"] = []

            if "history" not in db:
                db["history"] = []

            # =============================================
            # GLOBAL STATS
            # =============================================

            stats = {

                "wins": 0,

                "losses": 0,

                "total": 0,

                "rr_total": 0,

                "pairs": {}
            }

            # =============================================
            # PROCESS HISTORY
            # =============================================

            for s in db.get("history", []):

                symbol = s.get(
                    "symbol",
                    "UNKNOWN"
                )

                result = s.get(
                    "result",
                    "LOSS"
                )

                rr = s.get(
                    "rr",
                    "1:1"
                )

                stats["total"] += 1

                # =========================================
                # PAIR STORAGE
                # =========================================

                if symbol not in stats["pairs"]:

                    stats["pairs"][symbol] = {

                        "wins": 0,

                        "losses": 0,

                        "total": 0,

                        "rr_total": 0
                    }

                stats["pairs"][symbol]["total"] += 1

                # =========================================
                # RR EXTRACTION
                # =========================================

                try:

                    rr_value = float(
                        rr.split(":")[1]
                    )

                except:

                    rr_value = 1

                # =========================================
                # WIN
                # =========================================

                if result == "WIN":

                    stats["wins"] += 1

                    stats["rr_total"] += rr_value

                    stats["pairs"][symbol]["wins"] += 1

                    stats["pairs"][symbol]["rr_total"] += rr_value

                # =========================================
                # LOSS
                # =========================================

                elif result == "LOSS":

                    stats["losses"] += 1

                    stats["rr_total"] -= 1

                    stats["pairs"][symbol]["losses"] += 1

                    stats["pairs"][symbol]["rr_total"] -= 1

            # =============================================
            # STORE STATS
            # =============================================

            db["staffs"] = stats

            return db

        except Exception as e:

            logging.error(
                f"Load error: {e}"
            )

    # =====================================================
    # DEFAULT DATABASE
    # =====================================================

    return {

        "active": [],

        "history": [],

        "staffs": {

            "wins": 0,

            "losses": 0,

            "total": 0,

            "rr_total": 0,

            "pairs": {}
        }
    }

# =========================================================
# SAVE DATABASE
# =========================================================

def save_data(data):

    to_save = {

        "active": data.get(
            "active",
            []
        ),

        "history": data.get(
            "history",
            []
        )
    }

    with open(DB_FILE, "w") as f:

        json.dump(
            to_save,
            f,
            indent=2
        )

# =========================================================
# ACTIVE TRADE EVALUATION
# =========================================================

def evaluate_active_trades(db):

    still_active = []

    for trade in db.get("active", []):

        symbol = trade.get("symbol")

        interval = (

            "5min"

            if trade.get("strat")
            == "Hybrid Fake Breakout"

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

            high = float(
                last_candle['high']
            )

            low = float(
                last_candle['low']
            )

            tp = float(
                trade.get("tp", 0)
            )

            sl = float(
                trade.get("sl", 0)
            )

            trade_type = trade.get("type")

            was_hit = False

            result = None

            # =============================================
            # BUY TRADES
            # =============================================

            if trade_type == "BUY":

                if high >= tp:

                    was_hit = True

                    result = "WIN"

                elif low <= sl:

                    was_hit = True

                    result = "LOSS"

            # =============================================
            # SELL TRADES
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

                trade["closed_at"] = (
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )

                db["history"].insert(
                    0,
                    trade
                )

                logging.info(
                    f"Trade Closed: "
                    f"{symbol} hit {result}"
                )

            else:

                still_active.append(trade)

        except Exception as e:

            logging.error(
                f"Error checking active "
                f"trade {symbol}: {e}"
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

    except:

        return "index.html not found"

    # =====================================================
    # HISTORY TABLE
    # =====================================================

    history_rows = ""

    for s in db.get("history", [])[:50]:

        signal_class = (

            "buy-signal"

            if s.get("type") == "BUY"

            else "sell-signal"
        )

        result_class = (

            "buy-signal"

            if s.get("result") == "WIN"

            else "sell-signal"
        )

        history_rows += f"""
        <tr>
            <td class='pair-name'>{s.get('symbol')}</td>

            <td class='{signal_class}'>
                {s.get('type')}
            </td>

            <td>{s.get('entry')}</td>

            <td>{s.get('sl')}</td>

            <td>{s.get('tp')}</td>

            <td>{s.get('rr')}</td>

            <td class='{result_class}'>
                {s.get('result', '-')}
            </td>
        </tr>
        """

    # =====================================================
    # ACTIVE TABLE
    # =====================================================

    active_rows = ""

    for s in db.get("active", []):

        signal_class = (

            "buy-signal"

            if s.get("type") == "BUY"

            else "sell-signal"
        )

        active_rows += f"""
        <tr>
            <td class='pair-name'>{s.get('symbol')}</td>

            <td class='{signal_class}'>
                {s.get('type')}
            </td>

            <td>{s.get('entry')}</td>

            <td>{s.get('sl')}</td>

            <td>{s.get('tp')}</td>

            <td>{s.get('rr')}</td>

            <td class='cyan-status'>
                ACTIVE
            </td>
        </tr>
        """

    # =====================================================
    # PAIR STATS
    # =====================================================

    pair_html = ""

    staffs = db["staffs"]

    for pair, p_data in staffs["pairs"].items():

        total = p_data["total"]

        wins = p_data["wins"]

        rr_total = p_data["rr_total"]

        wr = (
            (wins / total) * 100
            if total > 0
            else 0
        )

        avg_rr = (
            round(rr_total / total, 2)
            if total > 0
            else 0
        )

        pair_html += f"""
        <div class="pair-card">

            <div class="p-name">
                {pair}
            </div>

            <div class="p-wr">
                {wr:.1f}%
            </div>

            <div class="p-count">
                {total} Signals
            </div>

            <div class="p-rr">
                Avg RR: {avg_rr}
            </div>

        </div>
        """

    # =====================================================
    # GLOBAL STATS
    # =====================================================

    total = staffs["total"]

    wins = staffs["wins"]

    losses = staffs["losses"]

    rr_total = staffs["rr_total"]

    global_wr = (

        (wins / total) * 100

        if total > 0

        else 0
    )

    avg_rr = (

        round(rr_total / total, 2)

        if total > 0

        else 0
    )

    last_scan = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # =====================================================
    # TEMPLATE REPLACEMENT
    # =====================================================

    html = template

    html = html.replace(
        "{{TOTAL}}",
        str(total)
    )

    html = html.replace(
        "{{WINRATE}}",
        f"{global_wr:.1f}%"
    )

    html = html.replace(
        "{{AVG_RR}}",
        str(avg_rr)
    )

    html = html.replace(
        "{{WINS}}",
        str(wins)
    )

    html = html.replace(
        "{{LOSSES}}",
        str(losses)
    )

    html = html.replace(
        "{{PAIR_STATS}}",
        pair_html
    )

    html = html.replace(
        "{{SIGNALS}}",
        history_rows
        or
        "<tr><td colspan='7'>"
        "No Closed Signals Yet"
        "</td></tr>"
    )

    html = html.replace(
        "{{ACTIVE_SIGNALS}}",
        active_rows
        or
        "<tr><td colspan='7'>"
        "No Active Signals"
        "</td></tr>"
    )

    html = html.replace(
        "{{LAST_SCAN}}",
        last_scan
    )

    return html

# =========================================================
# SCANNER
# =========================================================

@app.get("/scan")
def run_scanner():

    db = load_data()

    # =====================================================
    # MONITOR ACTIVE POSITIONS
    # =====================================================

    db = evaluate_active_trades(db)

    # =====================================================
    # FIND NEW SIGNALS
    # =====================================================

    new_found = engine.check_strategies()

    if new_found:

        for s in new_found:

            # =============================================
            # DUPLICATE PREVENTION
            # =============================================

            exists = any(

                x.get("symbol")
                == s.get("symbol")

                and

                x.get("entry")
                == s.get("entry")

                and

                x.get("type")
                == s.get("type")

                for x in db["active"]
            )

            if not exists:

                s["created"] = (
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )

                db["active"].insert(
                    0,
                    s
                )

    # =====================================================
    # SAVE
    # =====================================================

    save_data(db)

    return {

        "status": "complete",

        "new": len(new_found),

        "active": len(db["active"]),

        "history": len(db["history"])
    }

# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=10000
                )
