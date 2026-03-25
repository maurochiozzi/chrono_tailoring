import os
import sys
sys.path.insert(0, os.path.abspath('..'))

project = 'Chrono Tailoring'
copyright = '2024, Chrono Tailoring Team'
author = 'Chrono Tailoring Team'
release = '1.0'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'myst_parser',
    'sphinxcontrib.mermaid'
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'sphinx_rtd_theme'

# Configuration for LaTeX to guarantee PDF builds
latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '10pt',
    'preamble': '',
    'figure_align': 'htbp',
}
