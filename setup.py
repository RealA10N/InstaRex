from codecs import open
from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

# Get dependencies from requirements.txt file
with open(path.join(here, "requirements.txt")) as f:
    requirements_txt = f.read().splitlines()

setup(
    name="instarex",
    version="0.118.0",
    description="Develop Instagram bots with ease!",
    long_description=long_description,
    author="Alon Krymgand, Daniil Okhlopkov, Evgeny Kemerov",
    author_email="downtown2u@gmail.com, danokhlopkov@gmail.com, eskemerov@gmail.com",
    license="Apache Software License 2.0",
    url="https://github.com/reala10n/instarex",
    keywords=["instagram", "uploader", "bot", "api", "wrapper"],
    install_requires=requirements_txt,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    packages=find_packages(),
)
