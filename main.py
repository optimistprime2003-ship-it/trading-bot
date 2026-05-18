import os
import json
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine
from datetime import datetime

app = FastAPI()

DB_FILE = "data.json"

# =========================================================
# LOAD DATABASE
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

            # =====================================================
            # ADVANCED STATS ENGINE
            # =====================================================

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

            # =====================================================
            # PROCESS HISTORY
            # =====================================================

            for s in db.get("history", []):

                symbol = s.get("symbol", "UNKNOWN")

                strategy = s.get("strat", "UNKNOWN")

                rr_text = str(s.get("rr", "1:1"))

                stats["total"] += 1

                # =================================================
                # EXTRACT RR VALUE
                # =================================================

                try:

                    rr_value = float(rr_text.split(":")[1])

                except:

                    rr_value = 1.0

                # =================================================
                # PAIR STATS
                # =================================================

                if symbol not in stats["pairs"]:

                    stats["pairs"][symbol] = {

                        "wins": 0,
                        "losses": 0,
                        "total": 0,
                        "rr": 0
                    }

                stats["pairs"][symbol]["total"] += 1

                # =================================================
                # STRATEGY STATS
                # =================================================

                if strategy not in stats["strategies"]:

                    stats["strategies"][strategy] = {

                        "wins": 0,
                        "losses": 0,
                        "total": 0
                    }

                stats["strategies"][strategy]["total"] += 1

                # =================================================
                # WINS
                # =================================================

                if s.get("result") == "WIN":

                    stats["wins"] += 1

                    stats["rr_won"] += rr_value

                    stats["pairs"][symbol]["wins"] += 1

                    stats["pairs"][symbol]["rr"] += rr_value

                    stats["strategies"][strategy]["wins"] += 1

                # =================================================
                # LOSSES
                # =================================================

                elif s.get("result") == "LOSS":

                    stats["losses"] += 1

                    stats["rr_lost"] += 1

                    stats["pairs"][symbol]["losses"] += 1

                    stats["pairs"][symbol]["rr"] -= 1

                    stats["strategies"][strategy]["losses"] += 1

            # =====================================================
            # FINAL METRICS
            # =====================================================

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

                expectancy = (
                    stats["net_rr"] / stats["total"]
                )

                stats["expectancy"] = round(expectancy, 2)

            db["staffs"] = stats

            return db

        except Exception as e:

            logging.error(f"Load error: {e}")

    # =========================================================
    # EMPTY DATABASE
    # =========================================================

    return {

        "active": [],
        "history": [],

        "staffs": {

            "wins": 0,
            "losses": 0,
            "total": 0,

            "rr_won": 0,
            "rr_lost": 0,
            "net_rr": 0,

            "profit_factor": 0,
            "expectancy": 0,

            "pairs": {},
            "strategies": {}
        }
    }

# =========================================================
# SAVE DATABASE
# =========================================================

def save_data(data):

    to_save = {

        "active": data.get("active", []),

        "history": data.get("history", [])
    }

    with open(DB_FILE, "w") as f:

        json.dump(to_save, f, indent=2)

# =========================================================
# ACTIVE TRADE MONITOR
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

            high = float(last_candle['high'])

            low = float(last_candle['low'])

            tp = float(trade.get("tp", 0))

            sl = float(trade.get("sl", 0))

            trade_type = trade.get("type")

            was_hit = False

            result = None

            # =================================================
            # BUY
            # =================================================

            if trade_type == "BUY":

                if high >= tp:

                    was_hit = True

                    result = "WIN"

                elif low <= sl:

                    was_hit = True

                    result = "LOSS"

            # =================================================
            # SELL
            # =================================================

            elif trade_type == "SELL":

                if low <= tp:

                    was_hit = True

                    result = "WIN"

                elif high >= sl:

                    was_hit = True

                    result = "LOSS"

            # =================================================
            # CLOSE TRADE
            # =================================================

            if was_hit:

                trade["result"] = result

                trade["closed_at"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                db["history"].insert(0, trade)

                logging.info(
                    f"Trade Closed: {symbol} hit {result}"
                )

            else:

                still_active.append(trade)

        except Exception as e:

            logging.error(
                f"Error checking active trade {symbol}: {e}"
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

    for s in db.get("history", [])[:20]:

        color = (
            "#10b981"
            if s.get("type") == "BUY"
            else "#f43f5e"
        )

        result_color = (
            "#10b981"
            if s.get("result") == "WIN"
            else "#f43f5e"
        )

        history_rows += f"""
        <tr>
            <td>{s.get('symbol')}</td>
            <td style='color:{color};font-weight:700'>
                {s.get('type')}
            </td>
            <td>{s.get('entry')}</td>
            <td>{s.get('sl')}</td>
            <td>{s.get('tp')}</td>
            <td>{s.get('rr')}</td>
            <td style='color:{result_color};font-weight:700'>
                {s.get('result', '-')}
            </td>
        </tr>
        """

    # =====================================================
    # ACTIVE TABLE
    # =====================================================

    active_rows = ""

    for s in db.get("active", []):

        color = (
            "#10b981"
            if s.get("type") == "BUY"
            else "#f43f5e"
        )

        active_rows += f"""
        <tr>
            <td>{s.get('symbol')}</td>
            <td style='color:{color};font-weight:700'>
                {s.get('type')}
            </td>
            <td>{s.get('entry')}</td>
            <td>{s.get('sl')}</td>
            <td>{s.get('tp')}</td>
            <td>{s.get('rr')}</td>
            <td style='color:#38bdf8;font-weight:700'>
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

        wr = (
            (
                p_data['wins']
                / p_data['total']
            ) * 100
        ) if p_data['total'] > 0 else 0

        pair_html += f"""
        <div class="pair-card">
            <div class="p-name">{pair}</div>
            <div class="p-wr">{wr:.1f}%</div>
            <div class="p-count">
                {p_data['total']} Signals
            </div>
            <div class="p-count">
                RR: {p_data['rr']}
            </div>
        </div>
        """

    # =====================================================
    # GLOBAL WINRATE
    # =====================================================

    global_wr = (
        (
            staffs['wins']
            / staffs['total']
        ) * 100
    ) if staffs['total'] > 0 else 0

    last_scan = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # =====================================================
    # HTML REPLACEMENTS
    # =====================================================

    html = template.replace(
        "{{TOTAL}}",
        str(staffs['total'])
    )

    html = html.replace(
        "{{WINRATE}}",
        f"{global_wr:.1f}%"
    )

    html = html.replace(
        "{{TOTAL_WINS}}",
        str(staffs['wins'])
    )

    html = html.replace(
        "{{TOTAL_LOSSES}}",
        str(staffs['losses'])
    )

    html = html.replace(
        "{{RR_WON}}",
        str(round(staffs['rr_won'], 2))
    )

    html = html.replace(
        "{{RR_LOST}}",
        str(round(staffs['rr_lost'], 2))
    )

    html = html.replace(
        "{{NET_RR}}",
        str(round(staffs['net_rr'], 2))
    )

    html = html.replace(
        "{{PROFIT_FACTOR}}",
        str(staffs['profit_factor'])
    )

    html = html.replace(
        "{{EXPECTANCY}}",
        str(staffs['expectancy'])
    )

    html = html.replace(
        "{{PAIR_STATS}}",
        pair_html
    )

    html = html.replace(
        "{{SIGNALS}}",
        history_rows or
        "<tr><td colspan='7'>No Closed Signals Yet</td></tr>"
    )

    html = html.replace(
        "{{ACTIVE_SIGNALS}}",
        active_rows or
        "<tr><td colspan='7'>No Active Signals</td></tr>"
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

    db = evaluate_active_trades(db)

    new_found = engine.check_strategies()

    if new_found:

        for s in new_found:

            exists = any(

                x.get("symbol") == s.get("symbol")

                and x.get("entry") == s.get("entry")

                and x.get("type") == s.get("type")

                for x in db["active"]
            )

            if not exists:

                s["created"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                db["active"].insert(0, s)

        save_data(db)

    return {

        "status": "complete",

        "new": len(new_found)
    }

# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=10000
            )
