
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock app and DB
mock_app = MagicMock()
mock_db = MagicMock()
mock_app.db = mock_db
sys.modules['app'] = mock_app

# Mock models
mock_models = MagicMock()
sys.modules['models'] = mock_models

# Import Voice Processor
from voice_service import VoiceCommandProcessor


class TestVoiceBackend(unittest.TestCase):
    def test_create_invoice_cloud_client(self):
        # Setup
        processor = VoiceCommandProcessor()
        
        # Mock requests.get for Cloud API
        with patch('voice_service.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {"id": 101, "name": "Cloud Client A", "email": "a@cloud.com"},
                {"id": 102, "name": "Cloud Client B", "email": "b@cloud.com"}
            ]
            mock_get.return_value = mock_response
            
            # Command
            command = "Create invoice for Cloud Client A"
            
            # Execute
            result = processor.process(command)
            
            print(f"Command: '{command}'")
            print(f"Result: {result}")
            
            # Verification
            if result['success'] and result['client_name'] == "Cloud Client A":
                print("SUCCESS: Voice assistant found Cloud Client A from API.")
            else:
                print(f"FAILURE: Result was {result}")
                self.assertTrue(result['success'], "Should have succeeded")

if __name__ == "__main__":
    unittest.main()
