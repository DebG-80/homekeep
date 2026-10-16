"""Conversation orchestrator: a Strands agent that reaches HomeKeep only through MCP (TDD §4.4).

This package never imports `app.domain` or `app.store`: every effect goes through the loopback MCP
server over HTTP, which is the hackathon's "imported and actually called at runtime" rule.
"""
