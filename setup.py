from setuptools import setup, find_packages

setup(
    name="zutui",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "beautifulsoup4",
        "textual",
        "keyring"
    ],
    entry_points={
        'console_scripts': [
            'zutui=zut_app.zutui:main',
        ],
    },
)
