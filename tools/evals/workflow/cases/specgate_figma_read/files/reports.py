def users_csv(users):
    return "\n".join(",".join([u["name"], u["email"]]) for u in users if not u["archived"])
