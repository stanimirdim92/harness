LABELS = {"en": "Export", "de": "Exportieren"}
def label(lang):
    return LABELS[lang]
def click(callback):
    callback()
