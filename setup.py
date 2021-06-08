import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    python_requires='>=3.0',
    setup_requires=['setuptools_scm',],
    use_scm_version=True,
    zip_safe=True,
    name="caprica",
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
        'Development Status :: 4 - Beta',
	'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Topic :: Utilities',
    ],
    py_modules=['caprica',],
    data_files=[('data',[
                 'data/clockface-71.png',
                 'data/clockpip-close.png',
                 'data/clockpip-open.png',
                 'data/ISO-8859-1.png',
                 'data/unichr-0x0030a.png',
                 'data/unichr-0x0039b.png',
                 'data/unichr-0x00444.png',
                 'data/unichr-0x02026.png',
               ]),],
)
