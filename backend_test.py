#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime, timezone, timedelta
import subprocess
import time

class DayMinderAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.session_token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_result(self, test_name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name} - {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })

    def setup_test_user(self):
        """Create test user and session in MongoDB"""
        print("\n🔧 Setting up test user and session...")
        
        timestamp = int(time.time())
        self.user_id = f"test-user-{timestamp}"
        self.session_token = f"test_session_{timestamp}"
        
        # MongoDB commands to create test user and session
        mongo_commands = f'''
use('test_database');
db.users.insertOne({{
  user_id: "{self.user_id}",
  email: "test.user.{timestamp}@example.com",
  name: "Test User",
  picture: "https://via.placeholder.com/150",
  onboarding_completed: false,
  created_at: new Date()
}});
db.user_sessions.insertOne({{
  user_id: "{self.user_id}",
  session_token: "{self.session_token}",
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
}});
print("Test user created with session token: {self.session_token}");
'''
        
        try:
            result = subprocess.run(
                ['mongosh', '--eval', mongo_commands],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print(f"✅ Test user created: {self.user_id}")
                print(f"✅ Session token: {self.session_token}")
                return True
            else:
                print(f"❌ MongoDB setup failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ MongoDB setup error: {e}")
            return False

    def cleanup_test_data(self):
        """Clean up test data from MongoDB"""
        print("\n🧹 Cleaning up test data...")
        
        mongo_commands = '''
use('test_database');
db.users.deleteMany({email: /test\\.user\\./});
db.user_sessions.deleteMany({session_token: /test_session/});
db.habits.deleteMany({user_id: /test-user-/});
db.habit_completions.deleteMany({user_id: /test-user-/});
print("Test data cleaned up");
'''
        
        try:
            subprocess.run(['mongosh', '--eval', mongo_commands], timeout=30)
            print("✅ Test data cleaned up")
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")

    def make_request(self, method, endpoint, data=None, expected_status=200):
        """Make API request with session token"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if self.session_token:
            headers['Authorization'] = f'Bearer {self.session_token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)
            
            success = response.status_code == expected_status
            
            if success:
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                return False, f"Status {response.status_code}, expected {expected_status}"
                
        except Exception as e:
            return False, f"Request error: {str(e)}"

    def test_auth_endpoints(self):
        """Test authentication endpoints"""
        print("\n📋 Testing Authentication Endpoints...")
        
        # Test /auth/me
        success, result = self.make_request('GET', 'auth/me')
        if success and isinstance(result, dict) and 'user_id' in result:
            self.log_result("GET /auth/me", True)
        else:
            self.log_result("GET /auth/me", False, str(result))
        
        # Test complete onboarding
        success, result = self.make_request('POST', 'auth/complete-onboarding')
        self.log_result("POST /auth/complete-onboarding", success, str(result) if not success else "")
        
        # Test logout
        success, result = self.make_request('POST', 'auth/logout')
        self.log_result("POST /auth/logout", success, str(result) if not success else "")

    def test_habits_endpoints(self):
        """Test habits CRUD operations"""
        print("\n📋 Testing Habits Endpoints...")
        
        # Test get habits (should be empty initially)
        success, result = self.make_request('GET', 'habits')
        if success and isinstance(result, list):
            self.log_result("GET /habits", True)
        else:
            self.log_result("GET /habits", False, str(result))
        
        # Test initialize default habits
        success, result = self.make_request('POST', 'habits/initialize-defaults')
        self.log_result("POST /habits/initialize-defaults", success, str(result) if not success else "")
        
        # Test get habits after initialization
        success, habits = self.make_request('GET', 'habits')
        if success and isinstance(habits, list) and len(habits) > 0:
            self.log_result("GET /habits (after init)", True)
            self.test_habit_id = habits[0]['habit_id']  # Store for later tests
        else:
            self.log_result("GET /habits (after init)", False, str(habits))
            return
        
        # Test create new habit
        new_habit_data = {
            "name": "Test Habit",
            "color": "#3B82F6",
            "icon": "circle"
        }
        success, result = self.make_request('POST', 'habits', new_habit_data, 201)
        if success and isinstance(result, dict) and 'habit_id' in result:
            self.log_result("POST /habits", True)
            self.created_habit_id = result['habit_id']
        else:
            self.log_result("POST /habits", False, str(result))
        
        # Test update habit
        if hasattr(self, 'created_habit_id'):
            update_data = {"name": "Updated Test Habit"}
            success, result = self.make_request('PUT', f'habits/{self.created_habit_id}', update_data)
            self.log_result("PUT /habits/{id}", success, str(result) if not success else "")
        
        # Test delete habit
        if hasattr(self, 'created_habit_id'):
            success, result = self.make_request('DELETE', f'habits/{self.created_habit_id}')
            self.log_result("DELETE /habits/{id}", success, str(result) if not success else "")

    def test_completions_endpoints(self):
        """Test habit completions"""
        print("\n📋 Testing Completions Endpoints...")
        
        if not hasattr(self, 'test_habit_id'):
            print("⚠️ Skipping completions tests - no habit available")
            return
        
        # Test get completions for current month
        now = datetime.now()
        success, result = self.make_request('GET', f'completions?year={now.year}&month={now.month}')
        if success and isinstance(result, list):
            self.log_result("GET /completions", True)
        else:
            self.log_result("GET /completions", False, str(result))
        
        # Test toggle completion
        today = now.strftime('%Y-%m-%d')
        toggle_data = {
            "habit_id": self.test_habit_id,
            "date": today
        }
        success, result = self.make_request('POST', 'completions/toggle', toggle_data)
        if success and isinstance(result, dict) and 'completed' in result:
            self.log_result("POST /completions/toggle", True)
        else:
            self.log_result("POST /completions/toggle", False, str(result))

    def test_admin_endpoints(self):
        """Test admin endpoints"""
        print("\n📋 Testing Admin Endpoints...")
        
        # Test get admin stats
        success, result = self.make_request('GET', 'admin/stats')
        if success and isinstance(result, dict):
            expected_keys = ['total_users', 'total_habits', 'total_completions']
            if all(key in result for key in expected_keys):
                self.log_result("GET /admin/stats", True)
            else:
                self.log_result("GET /admin/stats", False, f"Missing keys: {expected_keys}")
        else:
            self.log_result("GET /admin/stats", False, str(result))
        
        # Test get admin users
        success, result = self.make_request('GET', 'admin/users')
        if success and isinstance(result, list):
            self.log_result("GET /admin/users", True)
        else:
            self.log_result("GET /admin/users", False, str(result))

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting DayMinder API Tests...")
        print(f"🌐 Testing against: {self.base_url}")
        
        # Setup test environment
        if not self.setup_test_user():
            print("❌ Failed to setup test environment")
            return False
        
        try:
            # Run all test suites
            self.test_auth_endpoints()
            self.test_habits_endpoints()
            self.test_completions_endpoints()
            self.test_admin_endpoints()
            
            # Print summary
            print(f"\n📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
            
            if self.tests_passed == self.tests_run:
                print("🎉 All tests passed!")
                return True
            else:
                print("⚠️ Some tests failed")
                return False
                
        finally:
            # Always cleanup
            self.cleanup_test_data()

def main():
    tester = DayMinderAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
