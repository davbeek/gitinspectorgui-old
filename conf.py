# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "GitinspectorGUI"
# author = "GitinspectorGUI Team"
# copyright = "GitinspectorGUI Team"
# version = "0.4.1"
# release = version

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = []

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# The master toctree document.
root_doc = "README"

# Add the orphan directive to suppress warnings about missing TOC
rst_prolog = """
.. orphan::
"""

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "nature"


# Do not include the sources as part of the html output.
# This also means that there will be no link to the sources on the top line
# of each web page.
html_copy_source = False

html_theme_options = {
    "nosidebar": True,
}
