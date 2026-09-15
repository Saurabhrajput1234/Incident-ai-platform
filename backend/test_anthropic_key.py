#!/usr/bin/env python3
"""Quick test to verify Anthropic API key is working."""
import asyncio
from app.ai_platform.services.llm_service import LLMService


async def test_api_key():
    """Test Anthropic API key with a simple LLM call."""
    try:
        llm = LLMService()
        
        # Simple test message
        messages = [
            {"role": "user", "content": "Say 'Anthropic API is working' and nothing else."}
        ]
        
        print("Testing Anthropic API key...")
        response = await llm.complete(messages=messages)
        print(f"✓ Success! Response: {response}")
        return True
        
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_api_key())
    exit(0 if success else 1)
