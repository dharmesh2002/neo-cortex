def role_of(email: str) -> str:
    local = email.split("@")[0].lower()
    words = set(local.replace(".", " ").replace("_", " ").replace("-", " ").split())
    def has(*keys):
        return any(k in words or (len(k) > 5 and k in local) for k in keys)
    if has("learning", "training", "talent", "development", "lnd", "hr", "careers", "career"):
        return "Learning & Talent"
    if has("vendor", "vendors", "supplier", "suppliers", "procurement", "sourcing", "purchasing"):
        return "Vendor / Procurement"
    if has("partner", "partners", "partnerships", "alliances"):
        return "Partnerships"
    if has("events", "education", "membership", "sponsor", "sponsorship"):
        return "Association"
    return "General"
