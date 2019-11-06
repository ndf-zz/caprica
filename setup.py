import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    python_requires='>=3.0',
    name="caprica",
    version="1.0.0",
    author="Nathan Fraser",
    author_email="ndf@metarace.com.au",
    description="Lightweight Galactica/DHI replacement",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ndf-zz/caprica",
    entry_points={
        'console_scripts': [
            'caprica=caprica:main',
        ],
    },
    classifiers=[
        'Development Status :: 1 - Planning',
	'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Topic :: Utilities',
    ],
    py_modules=['caprica',],
)

