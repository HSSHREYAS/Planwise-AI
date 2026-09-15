"""
PlanWise AI - Frontend API Client

Thin HTTP client wrapping all backend API calls.
Frontend should ONLY use this module to communicate with backend.
"""

import os
from typing import Any, Dict, Optional

import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL}/api/v1"
TIMEOUT = 180  # LLM can be slow


class APIClient:
    """HTTP client for PlanWise AI backend."""

    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url

    def health_check(self) -> Dict[str, Any]:
        """Check backend availability."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError:
            return {"status": "unavailable", "service": "planwise-api", "ollama_available": False}
        except Exception as e:
            return {"status": "error", "service": "planwise-api", "error": str(e)}

    def create_session(self) -> Optional[str]:
        """Create a new planning session. Returns session_id."""
        for attempt in range(3):
            try:
                resp = requests.post(f"{self.base_url}/sessions", json={}, timeout=30)
                resp.raise_for_status()
                return resp.json().get("session_id")
            except requests.Timeout:
                if attempt < 2:
                    import time
                    time.sleep(2)
                    continue
                print("Error creating session: timeout after retries")
                return None
            except Exception as e:
                print(f"Error creating session: {e}")
                return None
        return None

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session state."""
        try:
            resp = requests.get(f"{self.base_url}/sessions/{session_id}", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """
        Send a message to the planning agent.
        This is the primary interaction endpoint.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/sessions/{session_id}/messages",
                json={"message": message},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            return {
                "status": "error",
                "message": "Request timed out. The AI model may be processing a complex request. Please try again.",
            }
        except requests.ConnectionError:
            return {
                "status": "error",
                "message": "Cannot connect to the backend. Please ensure the server is running.",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"An error occurred: {str(e)}",
            }

    def get_plan(self, session_id: str) -> Optional[Dict]:
        """Get the current plan."""
        try:
            resp = requests.get(
                f"{self.base_url}/sessions/{session_id}/plan",
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def replan(self, session_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Request replanning with changed constraints."""
        try:
            resp = requests.post(
                f"{self.base_url}/sessions/{session_id}/replan",
                json={"changes": changes},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            return {"status": "error", "message": "Replanning timed out. Please try again."}
        except Exception as e:
            return {"status": "error", "message": f"Replanning failed: {str(e)}"}


# Module-level instance
api_client = APIClient()
