# Leaping

Leaping's pytest debugger is a simple, fast and lightweight omniscient debugger for Python. Leaping traces the execution of your code
and allows you to retroactively inspect the state of your program at any time, using an LLM-based debugger with natural language.

# Installation
``pip install leaping``

# Usage
``
pytest --leaping
``  

By default, pytest automatically discovers all the python tests within your project and runs them.

# Features
You can ask Leaping questions like:
- What was the value of variable x at this point?
- Why was variable y set to this value?
- Why am I not hitting function x?
- What changes can I make to this code to make this test pass?



