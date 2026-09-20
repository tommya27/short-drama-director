"""Compatibility import for callers using api.app from the project root."""
from backend.main import app
__all__ = ['app']
