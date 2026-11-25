from ui import LABEL, click
assert LABEL == "Export"
calls=[]
click(lambda: calls.append(1))
assert calls == [1]
