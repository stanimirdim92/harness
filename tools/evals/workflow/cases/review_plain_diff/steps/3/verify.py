from ui import LABEL, click
assert LABEL == "Download"
calls=[]
click(lambda: calls.append(1))
assert calls == [1]
