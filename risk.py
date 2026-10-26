def size_position(capital, risk_per_trade, entry_premium, stop_premium, lot_size, capital_fraction=0.5):
    if any(float(x) <= 0 for x in (capital, risk_per_trade, entry_premium, stop_premium, lot_size, capital_fraction)):
        raise ValueError("All values must be greater than zero.")
    if stop_premium >= entry_premium:
        raise ValueError("For option buying, stop premium must be below entry premium.")
    unit_risk = entry_premium - stop_premium
    lots_risk = int(risk_per_trade // (unit_risk * lot_size))
    lots_capital = int((capital * capital_fraction) // (entry_premium * lot_size))
    lots = max(0, min(lots_risk, lots_capital))
    quantity = lots * int(lot_size)
    return {
        "lots": lots,
        "quantity": quantity,
        "premium_cost": round(quantity * entry_premium, 2),
        "planned_loss": round(quantity * unit_risk, 2),
        "warning": "Excludes brokerage, taxes, bid/ask spread, slippage, gaps and execution risk."
    }
