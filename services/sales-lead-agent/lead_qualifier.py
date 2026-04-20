"""Lead qualification logic — determines if a lead is worth pursuing."""
from __future__ import annotations

import structlog

from config import settings
from models import LeadInboundEvent, SolarCalcResult

log = structlog.get_logger()

# Swiss cantons served (two-letter abbreviations, all caps)
# Empty set = serve all cantons
_SERVED_CANTONS: set[str] = (
    {c.strip().upper() for c in settings.served_cantons.split(",") if c.strip()}
    if settings.served_cantons
    else set()
)

# Minimum viable project types
_ELIGIBLE_PROJECT_TYPES = {"solar", "bess", "vzev", "combined"}


def qualify(lead: LeadInboundEvent) -> tuple[bool, str]:
    """Return (qualified: bool, reason: str).

    A lead is qualified if:
    1. project_type is one of the eligible types
    2. canton is served (or served_cantons is empty = all)
    3. estimated quote value meets the minimum threshold
    """
    if lead.project_type not in _ELIGIBLE_PROJECT_TYPES:
        return False, f"unsupported_project_type:{lead.project_type}"

    if _SERVED_CANTONS and lead.canton:
        if lead.canton.upper() not in _SERVED_CANTONS:
            return False, f"canton_not_served:{lead.canton}"

    # Rough pre-check: require at least some sizing data or skip value check
    if lead.roof_area_m2 is not None:
        calc = solar_calc(lead)
        if calc.quote_value_chf < settings.min_quote_value_chf:
            return False, f"below_min_value:{calc.quote_value_chf:.0f}_chf"

    return True, "ok"


def solar_calc(lead: LeadInboundEvent) -> SolarCalcResult:
    """Estimate system size and quote value from available lead data.

    Priority:
    1. roof_area_m2 → kWp (1 kWp ≈ 6–7 m² roof, use 6.5 m²/kWp)
    2. annual_consumption_kwh → size to cover ~80 % of consumption
    3. Fallback: default 10 kWp system
    """
    if lead.roof_area_m2 and lead.roof_area_m2 > 0:
        kwp = round(lead.roof_area_m2 / 6.5, 1)
    elif lead.annual_consumption_kwh and lead.annual_consumption_kwh > 0:
        # Size to produce ~80 % of annual consumption
        kwp = round((lead.annual_consumption_kwh * 0.80) / settings.solar_yield_kwh_per_kwp, 1)
    else:
        kwp = 10.0  # Default mid-size residential system

    kwp = max(3.0, min(kwp, 500.0))  # Clamp to realistic range

    annual_yield = round(kwp * settings.solar_yield_kwh_per_kwp, 0)
    co2_savings = round(annual_yield * settings.solar_co2_kg_per_kwh, 0)
    quote_value = round(kwp * settings.solar_price_per_kwp_chf, 0)

    # Very rough payback estimate: assume 25 % of generation value offsets grid
    # electricity cost at ~0.30 CHF/kWh
    annual_savings_chf = annual_yield * 0.30
    payback_years = round(quote_value / annual_savings_chf, 1) if annual_savings_chf > 0 else 0.0

    return SolarCalcResult(
        system_size_kwp=kwp,
        annual_yield_kwh=annual_yield,
        co2_savings_kg_per_year=co2_savings,
        quote_value_chf=quote_value,
        payback_years=payback_years,
    )
