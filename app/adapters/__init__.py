"""Outbound integration adapters (HTTP clients) for external APIs.

`app.adapters` may depend on `app.core` only. Concrete integrations
(Toss Investment API, DART, news providers, ...) live in later phases
as subclasses of `BaseApiClient`; no such integration is implemented
here yet.
"""
