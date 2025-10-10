"""
JSON Schema for high-density workflow input document.

This schema defines the structure for capturing user interactions and flows
on a website for automated test generation.
"""

from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, field_validator


class DOMElement(BaseModel):
    """Optional DOM element details for an action."""
    selector: str = Field(..., description="CSS selector for the element")
    xpath: Optional[str] = Field(None, description="XPath selector (alternative)")
    tag_name: str = Field(..., description="HTML tag name (e.g., 'button', 'input')")
    text_content: Optional[str] = Field(None, description="Text content of the element")
    attributes: Optional[dict[str, str]] = Field(None, description="Element attributes (id, class, etc.)")
    bounding_box: Optional[dict[str, float]] = Field(None, description="{x, y, width, height}")
    
    model_config = {"extra": "forbid"}


class ScrollPosition(BaseModel):
    """Scroll position coordinates."""
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)


class WorkflowAction(BaseModel):
    """A single action/step in the workflow."""
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    action_type: Literal['click', 'type', 'navigate', 'scroll', 'select', 'hover', 'wait'] = Field(
        ..., description="Type of action performed"
    )
    description: str = Field(..., description="Human-readable description of the step")
    screenshot_url: str = Field(..., description="URL or path to screenshot taken at this step")
    
    # Action-specific details
    target_url: Optional[str] = Field(None, description="For navigation actions")
    input_text: Optional[str] = Field(None, description="For typing actions")
    scroll_position: Optional[ScrollPosition] = Field(None, description="For scroll actions")
    
    # Optional DOM details
    dom_element: Optional[DOMElement] = Field(None, description="DOM element details")
    
    # Validation/assertion expectations
    expected_outcome: Optional[str] = Field(None, description="What should happen after this action")
    wait_for: Optional[str] = Field(None, description="What to wait for after action (selector, timeout)")
    
    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate ISO 8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")
        return v
    
    model_config = {"extra": "forbid"}


class Viewport(BaseModel):
    """Browser viewport dimensions."""
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)


class WorkflowMetadata(BaseModel):
    """Metadata about the workflow recording."""
    name: str = Field(..., description="Name/title of the workflow")
    description: str = Field(..., description="Overall description of what the workflow tests")
    created_at: str = Field(..., description="ISO 8601 timestamp")
    browser: Literal['chromium', 'firefox', 'webkit', 'chrome', 'safari', 'edge'] = Field(
        ..., description="Browser used"
    )
    viewport: Viewport = Field(..., description="Browser viewport dimensions")
    
    @field_validator('created_at')
    @classmethod
    def validate_created_at(cls, v: str) -> str:
        """Validate ISO 8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")
        return v
    
    model_config = {"extra": "forbid"}


class WorkflowInput(BaseModel):
    """Complete workflow input document schema."""
    metadata: WorkflowMetadata = Field(..., description="Workflow metadata")
    starting_url: str = Field(..., description="Initial URL where the flow begins")
    actions: list[WorkflowAction] = Field(..., min_length=1, description="Ordered list of actions in the flow")
    expected_final_state: Optional[str] = Field(None, description="Expected state at completion")
    
    model_config = {"extra": "forbid"}


# Example usage and validation
EXAMPLE_WORKFLOW = {
    "metadata": {
        "name": "User Login Flow",
        "description": "Tests the complete user authentication process",
        "created_at": "2025-10-10T22:38:00+05:30",
        "browser": "chromium",
        "viewport": {"width": 1920, "height": 1080},
    },
    "starting_url": "https://example.com",
    "actions": [
        {
            "timestamp": "2025-10-10T22:38:05+05:30",
            "action_type": "click",
            "description": "Click on 'Sign In' button",
            "screenshot_url": "screenshots/step_001.png",
            "dom_element": {
                "selector": "button.sign-in",
                "tag_name": "button",
                "text_content": "Sign In",
                "attributes": {"class": "sign-in btn-primary", "id": "signin-btn"}
            },
            "expected_outcome": "Login modal appears"
        },
        {
            "timestamp": "2025-10-10T22:38:07+05:30",
            "action_type": "type",
            "description": "Enter username in email field",
            "screenshot_url": "screenshots/step_002.png",
            "input_text": "user@example.com",
            "dom_element": {
                "selector": "input[name='email']",
                "tag_name": "input",
                "attributes": {"type": "email", "name": "email", "placeholder": "Email"}
            }
        },
        {
            "timestamp": "2025-10-10T22:38:10+05:30",
            "action_type": "type",
            "description": "Enter password",
            "screenshot_url": "screenshots/step_003.png",
            "input_text": "********",  # Actual password should be securely handled
            "dom_element": {
                "selector": "input[name='password']",
                "tag_name": "input",
                "attributes": {"type": "password", "name": "password"}
            }
        },
        {
            "timestamp": "2025-10-10T22:38:12+05:30",
            "action_type": "click",
            "description": "Click submit button",
            "screenshot_url": "screenshots/step_004.png",
            "dom_element": {
                "selector": "button[type='submit']",
                "tag_name": "button",
                "text_content": "Log In"
            },
            "expected_outcome": "User is redirected to dashboard",
            "wait_for": "nav.user-menu"
        }
    ],
    "expected_final_state": "User is logged in and dashboard is visible"
}


if __name__ == "__main__":
    # Validate the example using Pydantic
    try:
        workflow = WorkflowInput.model_validate(EXAMPLE_WORKFLOW)
        print("✓ Example workflow is valid")
        print(f"\nWorkflow: {workflow.metadata.name}")
        print(f"Steps: {len(workflow.actions)}")
        
        # Demonstrate JSON serialization
        print("\n--- JSON Schema ---")
        print(WorkflowInput.model_json_schema())
        
        # Demonstrate model export
        print("\n--- Serialized to JSON ---")
        print(workflow.model_dump_json(indent=2)[:500] + "...")
        
    except Exception as e:
        print(f"✗ Validation failed: {e}")
