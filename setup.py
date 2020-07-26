# https://packaging.python.org/en/latest/distributing.html
# https://github.com/pypa/sampleproject

from setuptools import setup, find_packages
from codecs import open
from os import path, system

import sys, re

here = path.abspath(path.dirname(__file__))

try:
    system('''pandoc -f markdown-raw_html -o '%(dest_rst)s' '%(src_md)s' ''' % {
                'dest_rst': path.join(here, 'README.rst'),
                'src_md':   path.join(here, 'README.md'),
                })

    with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
        long_description = f.read()

    # strip out any HTML comment|tag
    long_description = re.sub(r'<!--.*?-->', '', long_description,
                                                flags=re.DOTALL|re.MULTILINE)
    long_description = re.sub(r'<img.*?src=.*?>', '', long_description,
                                                flags=re.DOTALL|re.MULTILINE)

    with open(path.join(here, 'README.rst'), 'w', encoding='utf-8') as f:
        f.write(long_description)

except:
    print("Generation of the documentation failed. " + \
          "Do you have 'pandoc' installed?")

    long_description = __doc__

# load __version__, __doc__, _author, _license and _url
exec(open(path.join(here, 'gdb_ctrl', 'version.py')).read())

setup(
    name='python-gdb-ctrl',
    version=__version__,

    description=__doc__,
    long_description=long_description,

    url=_url,

    # Author details
    author=_author,
    author_email='use-github-issues@example.com',

    license=_license,

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Debuggers',

        'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',

        'Programming Language :: Python :: 3'
    ],

    python_requires='>=3.5',
    install_requires=['blessings', 'python-gdb-mi'],

    keywords='debugger gdb',

    packages=['gdb_ctrl'],
    data_files=[("", ["LICENSE"])]
)

