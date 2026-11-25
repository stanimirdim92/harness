def active_users(users):
    return [u for u in users if not u["archived"]]
