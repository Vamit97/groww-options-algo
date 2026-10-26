def size_position(capital, risk_per_trade, entry_premium, stop_premium, lot_size, capital_fraction=0.5):
    if any(x <= 0 for x in (capital, risk_per_trade, entry_premium, stop_premium, lot_size, capital_fraction)):
        raise ValueError("All inputs must be positive.")
    if stop_premium >= entry_premium:
        raise ValueError("For long option buying, stop premium must be below entry premium.")
    unit_risk = entry_premium - stop_premium
    lots_by_risk = int(risk_per_trade // (unit_risk * lot_size))
    lots_by_capital = int((capital * capital_fraction) // (entry_premium * lot_size))
    lots = max(0, min(lots_by_risk, lots_by_capital))
    qty = lots * lot_size
    return {
        "lots": lots,
        "quantity": qty,
        "premium_cost": round(qty * entry_premium, 2),
        "planned_loss": round(qty * unit_risk, 2),
        "warning": "Excludes charges, spread, slippage, gaps and order execution risk."
    }
