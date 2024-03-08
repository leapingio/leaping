from setuptools import setup

setup(
    name="leaping",
    version="0.1.5",
    entry_points={
        'console_scripts': [
            'leaping=leaping:main',
        ],
    },
    install_requires=[
        "pytest-leaping==0.1.3",
        "prompt_toolkit==3.0.20",
        "openai==1.12.0"
    ],
)
