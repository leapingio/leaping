# Leaping

Leaping's pytest debugger is a simple, fast and lightweight debugger for Python tests. Leaping traces the execution of your code
and allows you to retroactively inspect the state of your program at any time, using an LLM-based debugger with natural language. 

It does this by keeping track of all of the variable changes and other sources of non-determinism from within your code. 

# Installation
- ``pip install leaping``
- Please set the environment variable `OPENAI_API_KEY` to your GPT API key, if you plan on using GPT

# Usage
``
pytest --leaping
``  
By default, pytest automatically discovers all the python tests within your project and runs them. Once the test has been run, a CLI will open allowing you
to interact with the debugger.

When pytest starts up, you will be prompted to select a model. Right now, we support both Ollama and GPT-4.

# Features

You can ask Leaping questions like:
- Why am I not hitting function x?
- Why was variable y set to this value?
- What was the value of variable x at this point?
- What changes can I make to this code to make this test pass?



