# Docs

Key technologies here:

= Sphinx - documentation generator
- sphinx napoleon - allows inline docs to use Numpy or Google format - much more readable in source than reST.)
- sphinx-apidoc - generates api docs from the python sources
- sphinx-autobuild - regenerates the docs when source files change


## Development flow

in the root of the project, run

```
sphinx-autobuild docs docs/_build/html -H
```

This will build the project, and watch the files for changes, automatically reloading the page in the web browser.
