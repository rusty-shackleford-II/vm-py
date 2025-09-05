#!/usr/bin/env python3
"""
Site JSON Sanitizer

This module provides functions to sanitize site.json content to prevent ESLint errors
during the build process. It automatically escapes problematic characters that would
cause React/JSX linting issues.
"""

import json
import re
from typing import Any, Dict, List, Union


def sanitize_text_for_jsx(text: str) -> str:
    """
    Sanitize text content to be JSX-safe by escaping problematic characters.
    
    Args:
        text (str): The text to sanitize
        
    Returns:
        str: JSX-safe text with escaped characters
    """
    if not isinstance(text, str):
        return text
    
    # Don't sanitize URLs - they need to remain as valid URLs
    if text.startswith(('http://', 'https://', '//', 'data:', 'mailto:', 'tel:')):
        return text
    
    # Note: Single quotes/apostrophes are fine in React/JSX, no need to escape
    
    # Escape double quotes (use smart quotes for better appearance)
    # Replace opening quotes
    text = re.sub(r'^"', "&ldquo;", text)  # Quote at start of string
    text = re.sub(r'(\s)"', r"\1&ldquo;", text)  # Quote after whitespace
    
    # Replace closing quotes  
    text = re.sub(r'"$', "&rdquo;", text)  # Quote at end of string
    text = re.sub(r'"(\s)', r"&rdquo;\1", text)  # Quote before whitespace
    text = re.sub(r'"([.!?])', r"&rdquo;\1", text)  # Quote before punctuation
    
    # Handle remaining quotes (fallback to generic quotes)
    text = text.replace('"', "&quot;")
    
    # Only escape HTML entities that would break JSX parsing, but leave ampersands alone
    # since React can handle them fine and they're commonly used in business names
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    
    # Only escape ampersands if they're part of problematic HTML that could break JSX
    # but leave normal ampersands (like "English & Spanish") alone
    
    return text


def sanitize_value(value: Any) -> Any:
    """
    Recursively sanitize a value (string, dict, list, etc.) for JSX safety.
    
    Args:
        value: The value to sanitize
        
    Returns:
        The sanitized value
    """
    if isinstance(value, str):
        return sanitize_text_for_jsx(value)
    elif isinstance(value, dict):
        return {key: sanitize_value(val) for key, val in value.items()}
    elif isinstance(value, list):
        return [sanitize_value(item) for item in value]
    else:
        return value


def sanitize_site_json(site_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize an entire site.json data structure for JSX safety.
    
    Args:
        site_data (Dict[str, Any]): The site data to sanitize
        
    Returns:
        Dict[str, Any]: The sanitized site data
    """
    print("🧹 Sanitizing site.json for JSX compliance...")
    
    # Create a deep copy and sanitize
    sanitized_data = sanitize_value(site_data)
    
    # Count changes for reporting
    original_str = json.dumps(site_data, sort_keys=True)
    sanitized_str = json.dumps(sanitized_data, sort_keys=True)
    
    if original_str != sanitized_str:
        changes = len([c for c in original_str if c in "'\"&<>"]) - len([c for c in sanitized_str if c in "'\"&<>"])
        print(f"✅ Sanitized {abs(changes)} problematic characters")
    else:
        print("✅ No sanitization needed - content was already clean")
    
    return sanitized_data


def sanitize_site_json_file(input_path: str, output_path: str = None) -> str:
    """
    Sanitize a site.json file and optionally save to a new location.
    
    Args:
        input_path (str): Path to the input site.json file
        output_path (str, optional): Path to save sanitized file. If None, overwrites input.
        
    Returns:
        str: Path to the sanitized file
    """
    if output_path is None:
        output_path = input_path
    
    print(f"📁 Reading site.json from: {input_path}")
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            site_data = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to read site.json: {e}")
    
    # Sanitize the data
    sanitized_data = sanitize_site_json(site_data)
    
    # Write sanitized data
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(sanitized_data, f, indent=2, ensure_ascii=False)
        print(f"💾 Sanitized site.json saved to: {output_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to write sanitized site.json: {e}")
    
    return output_path


def preview_sanitization(site_data: Dict[str, Any]) -> None:
    """
    Preview what changes would be made during sanitization without modifying the data.
    
    Args:
        site_data (Dict[str, Any]): The site data to preview
    """
    print("🔍 Sanitization Preview:")
    print("=" * 50)
    
    def preview_value(value: Any, path: str = "") -> None:
        if isinstance(value, str) and any(char in value for char in "'\"&<>"):
            sanitized = sanitize_text_for_jsx(value)
            if sanitized != value:
                print(f"📍 {path}:")
                print(f"   Before: {repr(value)}")
                print(f"   After:  {repr(sanitized)}")
                print()
        elif isinstance(value, dict):
            for key, val in value.items():
                new_path = f"{path}.{key}" if path else key
                preview_value(val, new_path)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                new_path = f"{path}[{i}]" if path else f"[{i}]"
                preview_value(item, new_path)
    
    preview_value(site_data)
    print("=" * 50)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python site_sanitizer.py <input_file> [output_file]")
        print("       python site_sanitizer.py <input_file> --preview")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    if len(sys.argv) > 2 and sys.argv[2] == "--preview":
        # Preview mode
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                site_data = json.load(f)
            preview_sanitization(site_data)
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    else:
        # Sanitize mode
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
        
        try:
            result_path = sanitize_site_json_file(input_file, output_file)
            print(f"🎉 Sanitization complete: {result_path}")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
