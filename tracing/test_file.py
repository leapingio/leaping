class Person:
    def __init__(self, x):
        self.x = x

    def speak(self):
        return "hey"


def func(x):
    y = 3 * x
    z = y + 5

    p = Person(3)
    p.speak()

    return z + p.x

def func2(y):
    a = y * 2
    return func(a)


def test_failure():
    val = func2(3)
    k = 5
    for i in range(3000000):
        i ^= 2
    x = 3 / (val-26)
    assert val == 4