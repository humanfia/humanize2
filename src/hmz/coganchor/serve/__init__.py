"""The target half: carrying out on this machine what a client asks for.

Reached as ``hmz anchor``.  Nothing here may import from the agent half of
the package -- only :mod:`hmz.coganchor.proto` is shared -- because this is the
half that runs on the target, where there is no ptrace, no seccomp filter and
no guarantee of an x86-64 register map.
"""
