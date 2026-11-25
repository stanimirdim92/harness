def discount(total, member):
    if total >= 100 and member:
        return 10
    return 0


def clamp(n):
    if n < 0:
        return 0
    return n
