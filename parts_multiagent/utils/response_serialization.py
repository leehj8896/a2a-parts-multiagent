"""Utilities for JSON serialization of response objects.

This module provides common patterns for converting domain response objects
to JSON-serializable dictionaries for A2A agent communication.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass instance to a dictionary.
    
    Recursively converts nested dataclasses and handles common types.
    """
    if is_dataclass(obj):
        return asdict(obj)
    return obj


def response_to_json_dict(response: Any) -> dict[str, Any]:
    """Convert a response object to a JSON-serializable dictionary.
    
    Handles various response types:
    - dataclass: converted via asdict()
    - dict: returned as-is
    - str: wrapped in {"text": value}
    """
    if isinstance(response, dict):
        return response
    
    if is_dataclass(response):
        return asdict(response)
    
    if isinstance(response, str):
        raise TypeError("String response is not allowed. Only application/json is supported.")
    
    # Fallback for other types
    return {"data": str(response)}


def wrap_success_response(data: dict[str, Any] | None = None, message: str | None = None) -> dict[str, Any]:
    """Create a standard success response structure.
    
    Args:
        data: Response data dictionary
        message: Optional success message
        
    Returns:
        Standard response dict: {"status": "success", "data": {...}, "message": "..."}
    """
    response: dict[str, Any] = {"status": "success"}
    
    if data:
        response["data"] = data
    
    if message:
        response["message"] = message
    
    return response


def wrap_error_response(error_message: str, error_code: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a standard error response structure.
    
    Args:
        error_message: Error message
        error_code: Optional error code
        details: Optional error details
        
    Returns:
        Standard error response dict: {"status": "error", "message": "...", "code": "...", "details": {...}}
    """
    response: dict[str, Any] = {
        "status": "error",
        "message": error_message,
    }
    
    if error_code:
        response["code"] = error_code
    
    if details:
        response["details"] = details
    
    return response
