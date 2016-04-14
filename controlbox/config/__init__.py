"""
A simple configuration helper build on top of ConfigObj that allows configuration files to be
layered - netural / os-specific, with a schema to validate the types of the config data.

Can be used to configure global values in modules, which we use for configuring integration test cases.
"""