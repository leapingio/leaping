from setuptools import setup

setup(
    name="leaping",
    version="0.1.0",
    entry_points={
        'console_scripts': [
            'leaping=leaping:main',
        ],
    },
)
