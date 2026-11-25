from pricing import discount, clamp
assert discount(150, True) == 10
assert discount(50, True) == 0
assert discount(150, False) == 0
assert clamp(5) == 5
assert clamp(-3) == 0
