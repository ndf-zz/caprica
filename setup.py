from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    python_requires='>=3.0',
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    name="caprica",
    version="1.0.0",
    packages=find_packages(),
    author="Nathan Fraser",
    author_email="ndf@metarace.com.au",
    description="Galactica/DHI replacement",
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
    include_package_data=True,
)

