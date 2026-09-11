"""Cross-cutting concerns shared by every other module: settings,
structured logging, and the application exception hierarchy.

`app.core` must not import from any other `app.*` package - everything
else depends on it, never the other way around.
"""
