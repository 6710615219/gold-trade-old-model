import os
import json
import numpy as np
import pandas as pd
from datetime import datetime


class AdvancedTradingAnalytics:
    @staticmethod
    def calculate_days_held(buy_date, sell_date):
        fmt = "%Y-%m-%d %H:%M:%S"
        b_date = datetime.strptime(buy_date, fmt) if isinstance(buy_date, str) else buy_date
        s_date = datetime.strptime(sell_date, fmt) if isinstance(sell_date, str) else sell_date
        days = (s_date - b_date).total_seconds() / 86400.0
        return max(days, 0.0001)

    @staticmethod
    def calculate_annualized_return(profit_pct, days_held):
        r = profit_pct / 100.0
        safe_days = max(days_held, 1.0)
        return (((1 + r) ** (365.0 / safe_days)) - 1) * 100.0

    @staticmethod
    def generate_full_report(closed_trades, unrealized_pl, current_nav, first_date, starting_capital=1500.0):
        if not closed_trades:
            return {
                "Total Closed Trade": 0,
                "Win Rate (%)": 0.0,
                "Total Profit (THB)": 0.0,
                "Unrealized P/L (THB)": round(unrealized_pl, 2),
                "Average Win (THB)": 0.0,
                "Average Loss (THB)": 0.0,
                "Expectancy per Trade (THB)": 0.0,
                "Best Annualized Trade (%)": 0.0,
                "Worst Annualized Trade (%)": 0.0,
                "Median Annualized Trade (%)": 0.0,
                "Top 10% Annualized Trade (%)": 0.0,
                "Bottom 10% Annualized Trade (%)": 0.0,
                "XIRR (%)": 0.0,
                "Avg Capital/Year (THB)": 0.0,
                "Sharpe Ratio": 0.0
            }

        total_trades = len(closed_trades)
        profits = [t['sell_amount'] - t['buy_amount'] for t in closed_trades]
        winning_trades = [p for p in profits if p > 0]
        losing_trades = [p for p in profits if p <= 0]

        total_profit = sum(profits)
        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        avg_win = np.mean(winning_trades) if winning_trades else 0
        avg_loss = abs(np.mean(losing_trades)) if losing_trades else 0

        win_prob = win_rate / 100.0
        expectancy = (win_prob * avg_win) - ((1.0 - win_prob) * avg_loss)

        ann_returns = []
        for t in closed_trades:
            p_pct = ((t['sell_amount'] - t['buy_amount']) / t['buy_amount']) * 100 if t['buy_amount'] > 0 else 0
            ann_returns.append(AdvancedTradingAnalytics.calculate_annualized_return(p_pct, t['days_held']))

        ann_returns.sort()
        returns_array = np.array(ann_returns)
        excess_returns = returns_array - 2.0
        std_dev = np.std(excess_returns, ddof=1) if len(excess_returns) > 1 else 0
        sharpe = np.mean(excess_returns) / std_dev if std_dev != 0 else 0.0

        median_ann = np.median(ann_returns) if ann_returns else 0

        n_10_percent = max(1, int(len(ann_returns) * 0.10))
        top_10_ann = np.mean(ann_returns[-n_10_percent:]) if ann_returns else 0
        bottom_10_ann = np.mean(ann_returns[:n_10_percent]) if ann_returns else 0

        avg_capital_year = sum((t['buy_amount'] * t['days_held']) / 365.0 for t in closed_trades)

        fmt = "%Y-%m-%d %H:%M:%S"
        try:
            start_dt = datetime.strptime(first_date, fmt)
        except:
            start_dt = datetime.now()

        days_total = max((datetime.now() - start_dt).total_seconds() / 86400.0, 1.0)
        xirr = (((current_nav / starting_capital) ** (365.0 / days_total)) - 1) * 100.0

        return {
            "Total Closed Trade": total_trades,
            "Win Rate (%)": round(win_rate, 2),
            "Total Profit (THB)": round(total_profit, 2),
            "Unrealized P/L (THB)": round(unrealized_pl, 2),
            "Average Win (THB)": round(avg_win, 2),
            "Average Loss (THB)": round(avg_loss, 2),
            "Expectancy per Trade (THB)": round(expectancy, 2),
            "Best Annualized Trade (%)": round(max(ann_returns), 2) if ann_returns else 0.0,
            "Worst Annualized Trade (%)": round(min(ann_returns), 2) if ann_returns else 0.0,
            "Median Annualized Trade (%)": round(median_ann, 2),
            "Top 10% Annualized Trade (%)": round(top_10_ann, 2),
            "Bottom 10% Annualized Trade (%)": round(bottom_10_ann, 2),
            "XIRR (%)": round(xirr, 2),
            "Avg Capital/Year (THB)": round(avg_capital_year, 2),
            "Sharpe Ratio": round(sharpe, 2)
        }


def parse_logs_to_metrics(log_file_name, current_sell_price_per_g, baht_to_gram=15.244):
    logs = []
    if os.path.isfile(log_file_name):
        with open(log_file_name, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except:
                pass

    open_lots = []
    closed_trades = []

    first_date = logs[0].get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")) if logs else datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S")

    for log in logs:
        act = log.get("executed_action")
        date_str = log.get("date")
        amt_str = str(log.get("amount", ""))

        if act == "BUY":
            try:
                grams = float(amt_str.split(" ")[0].rstrip("g"))
                thb = float(amt_str.split("(")[1].split(" ")[0].replace(",", ""))
                price_per_g = thb / grams
                open_lots.append({"grams": grams, "thb": thb, "price_per_g": price_per_g, "date": date_str})
            except:
                pass

        elif act == "SELL":
            try:
                grams_sold = float(amt_str.split("Sold ")[1].split(" ")[0].rstrip("g"))
                thb_received = float(amt_str.split("(")[1].split(" ")[0].replace(",", ""))
                sell_price_per_g = thb_received / grams_sold

                while grams_sold > 0 and open_lots:
                    lot = open_lots[0]

                    if lot["grams"] <= grams_sold:
                        buy_amt = lot["thb"]
                        sell_amt = lot["grams"] * sell_price_per_g
                        days_held = AdvancedTradingAnalytics.calculate_days_held(lot["date"], date_str)
                        closed_trades.append({"buy_amount": buy_amt, "sell_amount": sell_amt, "days_held": days_held})

                        grams_sold -= lot["grams"]
                        open_lots.pop(0)
                    else:
                        buy_amt = grams_sold * lot["price_per_g"]
                        sell_amt = grams_sold * sell_price_per_g
                        days_held = AdvancedTradingAnalytics.calculate_days_held(lot["date"], date_str)
                        closed_trades.append({"buy_amount": buy_amt, "sell_amount": sell_amt, "days_held": days_held})

                        lot["grams"] -= grams_sold
                        grams_sold = 0

            except:
                pass

    unrealized_pl = sum(lot["grams"] * (current_sell_price_per_g - lot["price_per_g"]) for lot in open_lots)

    return closed_trades, unrealized_pl, first_date
