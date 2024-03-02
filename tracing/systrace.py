import sys

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

from simpletracer import SimpleTracer

tracer = SimpleTracer()

sys.settrace(tracer.simple_tracer)
print(func2(3))
sys.settrace(None)


for (file_path, func_name), mappings in tracer.function_to_mapping.items(): 
    print(file_path, func_name)
    for line_no, ast_assignments in mappings.items():
        print(line_no, ast_assignments)

for (file_path, func_name, line_no), deltas in tracer.function_to_deltas.items():
    print(file_path, func_name, line_no)
    for delta in deltas:
        print(delta)
    
