def role_of(email: str) -> str:
    local = email.split("@")[0].lower()
    words = set(local.replace(".", " ").replace("_", " ").replace("-", " ").split())
    def has(*keys):
        return any(k in words or (len(k) > 4 and k in local) for k in keys)
    if has("career", "careers", "internship", "jobs"):
        return "Career Services"
    if has("employer", "employers", "partner", "partners", "partnerships", "corporate"):
        return "Employer Partnerships"
    if has("continuing", "workforce", "training", "ce"):
        return "Continuing Ed / Workforce"
    if has("him", "informatics", "program", "programs", "chair", "director", "hit", "healthinformatics"):
        return "Program"
    if has("admission", "admissions", "enroll", "advising", "advisor"):
        return "Admissions / Advising"
    if has("membership", "chapter", "events", "education"):
        return "Association"
    return "General"
