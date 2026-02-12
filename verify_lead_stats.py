
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock app and models modules BEFORE importing analytics_engine
mock_app = MagicMock()
mock_db = MagicMock()
mock_app.db = mock_db
sys.modules['app'] = mock_app

mock_models = MagicMock()
sys.modules['models'] = mock_models

# Now import AnalyticsEngine
from analytics_engine import AnalyticsEngine

class TestLeadStats(unittest.TestCase):
    def test_get_lead_stats_cloud(self):
        # Mock db_session as it's not used in the new get_lead_stats but required for init
        mock_db_session = MagicMock()
        engine = AnalyticsEngine(mock_db_session)
        
        # Mock requests.get to return sample cloud data
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            
            # Simulate cloud response with various lead stages
            cloud_data = [
                {'id': 1, 'name': 'Client A', 'lead_stage': 'New'},
                {'id': 2, 'name': 'Client B', 'lead_stage': 'new'}, # Case insensitive check
                {'id': 3, 'name': 'Client C', 'lead_stage': 'Discussion'},
                {'id': 4, 'name': 'Client D', 'lead_stage': 'Proposal Sent'},
                {'id': 5, 'name': 'Client E', 'lead_stage': 'Closed Won'},
                {'id': 6, 'name': 'Client F'} # No stage, should default to New
            ]
            
            mock_response.json.return_value = cloud_data
            mock_get.return_value = mock_response
            
            stats = engine.get_lead_stats()
            
            print("Calculated Stats:", stats)
            
            # Logic check:
            # New: Client A (New), Client B (new), Client F (default) -> 3
            # Discussion: Client C (Discussion) -> 1
            # Quoted: Client D (Proposal Sent matches 'proposal') -> 1
            # Closed: Client E (Closed Won matches 'closed') -> 1
            
            self.assertEqual(stats['new'], 3, "New count mismatch") 
            self.assertEqual(stats['discussion'], 1, "Discussion count mismatch")
            self.assertEqual(stats['quoted'], 1, "Quoted count mismatch")
            self.assertEqual(stats['closed'], 1, "Closed count mismatch")

if __name__ == '__main__':
    unittest.main()
