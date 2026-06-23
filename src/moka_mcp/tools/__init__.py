"""Moka MCP Tools 注册入口。"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import candidates, departments, jobs, offers, pipelines, talent_pools


def register_all(mcp: FastMCP) -> None:
    """把所有模块的 Tool 注册到 MCP Server。"""
    candidates.register(mcp)
    jobs.register(mcp)
    pipelines.register(mcp)
    departments.register(mcp)
    offers.register(mcp)
    talent_pools.register(mcp)
