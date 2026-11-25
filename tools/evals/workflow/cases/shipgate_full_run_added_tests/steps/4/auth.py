ALLOWED = {"admin", "owner"}

def can_export(user):
    return user is not None and user.get("role") in ALLOWED
