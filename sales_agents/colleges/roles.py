def role_of(email: str) -> str:
    local = email.split("@")[0].lower()
    for keys, label in ((("placement", "tpo", "tnp", "training", "career", "industry"), "Placement"),
                        (("hod", "cse", "comp", "it", "ce", "mca", "bca"), "Department"),
                        (("principal", "director", "dean", "registrar"), "Principal / Leadership"),
                        (("admission",), "Admissions")):
        if any(k == local or k in local.replace(".", " ").replace("_", " ").replace("-", " ").split() or
               (len(k) > 3 and k in local) for k in keys):
            return label
    return "General"
