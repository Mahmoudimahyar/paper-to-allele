# Compensation-specific agent rules
- Compensation is a separate bounded context and presentation concern.
- It must never influence or be readable by matching computation.
- No negotiation/payment endpoints.
- Amounts are integer rials with derived toman display; changes are versioned.
