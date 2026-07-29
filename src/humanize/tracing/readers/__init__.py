"""One reader per backend, each turning its own log format into the shared session model.

A backend is driven one way and logs another, and the two have nothing in common but the
name of the backend -- so what reads a trajectory back lives here rather than beside what
wrote it. Where the logs are is not read from here: :mod:`humanize.backends` says that.
"""
