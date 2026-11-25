from ui import LABEL, click
assert LABEL == "Fetch"
calls=[]
assert click({"role": "viewer"}, lambda: calls.append(1)) is False and calls == []
assert click({"role": "admin"}, lambda: calls.append(1)) is True and calls == [1]
