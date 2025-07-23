"""
Script to make the first user (or any user by email) an admin.
Usage:
    python -m scripts.make_first_admin
    python -m scripts.make_first_admin --email user@company.com
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from backend.database import SessionLocal
from backend.models.auth_models import User


def make_admin(email: str = None):
    """Make a user an admin by email or just the first user"""
    db = SessionLocal()
    
    try:
        if email:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                print(f"❌ User with email '{email}' not found")
                return False
        else:
            # Get the first user
            user = db.query(User).order_by(User.id).first()
            if not user:
                print("❌ No users found in database")
                print("Please have at least one user log in first")
                return False
        
        # Update user to admin
        user.is_superuser = True
        if user.roles is None:
            user.roles = []
        if "admin" not in user.roles:
            user.roles = user.roles + ["admin"]
        
        db.commit()
        
        print(f"✅ Successfully made {user.email} an admin!")
        print(f"   Name: {user.full_name}")
        print(f"   ID: {user.id}")
        print(f"   Roles: {user.roles}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def list_users():
    """List all users in the database"""
    db = SessionLocal()
    
    try:
        users = db.query(User).order_by(User.id).all()
        
        if not users:
            print("No users found in database")
            return
        
        print("\nCurrent users:")
        print("-" * 80)
        print(f"{'ID':<5} {'Email':<30} {'Name':<25} {'Admin':<8} {'Active':<8}")
        print("-" * 80)
        
        for user in users:
            print(f"{user.id:<5} {user.email:<30} {user.full_name or 'N/A':<25} "
                  f"{'Yes' if user.is_superuser else 'No':<8} "
                  f"{'Yes' if user.is_active else 'No':<8}")
        
        print("-" * 80)
        print(f"Total users: {len(users)}")
        
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Make a user an admin in the Internal Edge Tool"
    )
    parser.add_argument(
        "--email",
        help="Email of the user to make admin (defaults to first user)",
        default=None
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all users instead of making admin"
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_users()
    else:
        make_admin(args.email)


if __name__ == "__main__":
    main()
