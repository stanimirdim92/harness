from auth import can_export
LABEL = "Download"
def click(user, callback):
    if not can_export(user):
        return False
    callback()
    return True
