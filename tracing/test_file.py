class Person:
    def __init__(self, x):
        self.x = x

    def speak(self):
        return "hey"

    def introduce(self):
        msg = self.speak()
        return f"{msg}, I'm a person with attribute x = {self.x}"

    def calculate(self):
        return self.x * 2

    def react(self):
        reaction = self.introduce() + ". Nice to meet you!"
        return reaction

    def conclude(self):
        conclusion = self.react() + " Let's calculate something: " + str(self.calculate())
        return conclusion

def func(x):
    y = 3 * x
    z = y + 5

    p = Person(3)
    result = p.conclude()  # Modified to use the conclude method

    return z + p.x

def func2(y):
    a = y * 2
    return func(a)

def func3(z):
    return func2(z + 1)

def func4(w):
    return func3(w * 2)

def test_failure():
    val = func4(3)  # Changed to call func4
    k = 5
    for i in range(300000):
        i ^= 2
    x = 3 / (val - 26)
    assert val == 4
