from ui import label, click
assert label("en") == "Export"
assert label("de") == "Exportieren"
calls=[]
click(lambda: calls.append(1))
assert calls == [1]
