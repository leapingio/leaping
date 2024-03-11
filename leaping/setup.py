from setuptools import setup

setup(
    name="leaping",
    version="0.1.6",
    entry_points={
        'console_scripts': [
            'leaping=leaping:main',
        ],
    },
    python_requires='>=3.12',
    install_requires=[
        "pytest-leaping==0.1.6",
        "prompt_toolkit==3.0.20",
        "openai==1.12.0"
    ],
)
