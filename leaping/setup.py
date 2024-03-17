from setuptools import setup

setup(
    name="leaping",
    version="0.1.8",
    entry_points={
        'console_scripts': [
            'leaping=leaping:main',
        ],
    },
    python_requires='>=3.0',
    install_requires=[
        "pytest-leaping==0.1.7",
        "prompt_toolkit==3.0.20",
        "openai==1.12.0"
    ],
)
