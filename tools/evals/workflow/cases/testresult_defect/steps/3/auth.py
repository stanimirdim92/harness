ALLOWED = {"admin"}

def can_export(user):
    return user.get("role") in ALLOWED
